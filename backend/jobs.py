"""One-at-a-time job runner. Videos are processed in order; the site polls for status."""
import logging
import shutil
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import accounts
import keyframes
import settings
from errors import UserError

log = logging.getLogger("mobiphysio.jobs")


class JobManager:
    def __init__(self):
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="analyze")
        self._lock = threading.Lock()
        self.jobs = {}

    def _active(self):
        return sum(1 for j in self.jobs.values() if j["status"] in ("queued", "processing", "scoring"))

    def submit(self, engine, video_path, code, user_id=None, video_name=None):
        """Queues a job. Returns (job_id, future). Raises UserError(503) if the queue is full.
        With a user_id the finished assessment is saved to that user's account."""
        with self._lock:
            if self._active() >= settings.QUEUE_MAX + 1:
                raise UserError(503, "The server is busy. Try again shortly.")
            job_id = uuid.uuid4().hex
            self.jobs[job_id] = {"status": "queued", "created": time.time(), "exercise": code,
                                 "user_id": user_id, "video_name": video_name}
        future = self._pool.submit(self._run, engine, video_path, code, job_id)
        return job_id, future

    def _set(self, job_id, **kw):
        with self._lock:
            self.jobs[job_id].update(kw)

    def _run(self, engine, video_path, code, job_id):
        try:
            result = engine.analyze(video_path, code, job_id, on_stage=lambda s: self._set(job_id, status=s))
            # key frames for the PDF report, taken now because the video is deleted below
            gif = settings.OUTPUT_DIR / f"{job_id}.gif"
            frames = keyframes.extract(video_path, gif, settings.OUTPUT_DIR / job_id / "keyframes")
            saved_id = None
            user_id = self.jobs[job_id]["user_id"]
            if user_id is not None:
                try:
                    saved_id = accounts.save_assessment(user_id, code, result["score"], result["details"],
                                                        self.jobs[job_id]["video_name"], gif, frames)
                except Exception:
                    log.exception("Job %s: could not save the assessment", job_id)
            result = {**result, "job_id": job_id, "assessment_id": saved_id}
            self._set(job_id, status="done", result=result, keyframes=frames)
            return result
        except UserError as e:
            self._set(job_id, status="failed", detail=e.message, code=e.status_code)
            shutil.rmtree(settings.OUTPUT_DIR / job_id, ignore_errors=True)
            raise
        except Exception:
            log.exception("Job %s failed", job_id)
            msg = "Something went wrong while analysing the video."
            self._set(job_id, status="failed", detail=msg, code=500)
            shutil.rmtree(settings.OUTPUT_DIR / job_id, ignore_errors=True)
            raise UserError(500, msg)
        finally:
            video_path.unlink(missing_ok=True)        # uploaded videos are never kept

    def mark_saved(self, job_id, assessment_id):
        with self._lock:
            job = self.jobs.get(job_id)
            if job and job.get("result"):
                job["result"] = {**job["result"], "assessment_id": assessment_id}

    def get(self, job_id):
        with self._lock:
            j = self.jobs.get(job_id)
            return dict(j) if j else None

    def cleanup(self):
        """Forget finished jobs older than JOB_TTL_HOURS and delete their files."""
        cutoff = time.time() - settings.JOB_TTL_HOURS * 3600
        with self._lock:
            old = [k for k, j in self.jobs.items()
                   if j["created"] < cutoff and j["status"] in ("done", "failed")]
            for k in old:
                del self.jobs[k]
        for k in old:
            (settings.OUTPUT_DIR / f"{k}.gif").unlink(missing_ok=True)
            shutil.rmtree(settings.OUTPUT_DIR / k, ignore_errors=True)
