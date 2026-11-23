"""
MobiPhysio backend.

Run (from this folder):
    uvicorn main:app --port 8000
Then open http://localhost:8000  (this server also serves the website).

Endpoints match frontend/js/config.js:
    POST /api/analyze           multipart: video, exercise_id
    GET  /api/status/{job_id}   poll mode only
    GET  /outputs/<job>.gif     skeleton GIF
    GET  /api/health            models loaded? CPU or GPU?
"""
import asyncio
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import settings
from errors import UserError
from jobs import JobManager
from routing import EXERCISES
from pipeline import probe_video, check_length

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(settings.LOG_DIR / "backend.log", encoding="utf-8")],
)
log = logging.getLogger("mobiphysio")

STATE = {"engine": None, "ready": False}
JOBS = JobManager()


async def _cleanup_loop():
    while True:
        await asyncio.sleep(600)
        JOBS.cleanup()


@asynccontextmanager
async def lifespan(app: FastAPI):
    from regressors import prepare_all
    from pipeline import Engine

    log.info("Checking the 9 models...")
    entries = await run_in_threadpool(prepare_all)        # raises -> server does not start
    log.info("Loading YOLO26-pose, KTPFormer and the 9 encoders...")
    STATE["engine"] = await run_in_threadpool(Engine, entries)
    STATE["ready"] = True
    log.info("Ready. Mode: %s. Open http://localhost:8000", settings.MODE)
    task = asyncio.create_task(_cleanup_loop())
    yield
    task.cancel()


app = FastAPI(title="MobiPhysio API", lifespan=lifespan)

# Only needed when the site is served from a different address than this API.
# Replace "*" with the real site address before going public.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.exception_handler(UserError)
async def _user_error(_: Request, e: UserError):
    return JSONResponse(status_code=e.status_code, content={"detail": e.message})


@app.exception_handler(Exception)
async def _crash(_: Request, e: Exception):
    log.exception("Unhandled error")
    return JSONResponse(status_code=500, content={"detail": "Something went wrong while analysing the video."})


def _save_upload(video: UploadFile) -> Path:
    suffix = Path(video.filename or "").suffix.lower()
    if suffix not in settings.ALLOWED_EXTENSIONS:
        raise UserError(415, "Only .mp4, .mov, .webm and .mkv videos are accepted.")
    path = settings.UPLOAD_DIR / f"{uuid.uuid4().hex}{suffix}"
    with path.open("wb") as f:
        shutil.copyfileobj(video.file, f, length=1 << 20)
    return path


@app.post("/api/analyze")
async def analyze(video: Optional[UploadFile] = File(None), exercise_id: Optional[str] = Form(None)):
    if exercise_id not in EXERCISES:
        raise UserError(400, "This exercise is not supported.")
    if video is None or not video.filename:
        raise UserError(400, "No video was uploaded.")
    if not STATE["ready"]:
        raise UserError(503, "The assessment model is not ready. Try again in a few minutes.")

    path = await run_in_threadpool(_save_upload, video)
    try:
        # quick checks first, so a bad file is rejected at once, before any model runs
        _frames, _fps, _w, _h, seconds = await run_in_threadpool(probe_video, path)
        check_length(seconds)
        job_id, future = JOBS.submit(STATE["engine"], path, exercise_id)
    except UserError:
        path.unlink(missing_ok=True)
        raise
    log.info("Job %s: %s", job_id, EXERCISES[exercise_id].name)

    if settings.MODE == "poll":
        return {"job_id": job_id}
    return await asyncio.wrap_future(future)     # sync: wait; UserError propagates to the handler


@app.get("/api/status/{job_id}")
def status(job_id: str):
    job = JOBS.get(job_id)
    if job is None:
        raise UserError(404, "This analysis was not found or has expired.")
    body = {"status": job["status"]}
    if job["status"] == "done":
        body.update(job["result"])
    elif job["status"] == "failed":
        body["detail"] = job["detail"]
    return body


@app.get("/api/health")
def health():
    eng = STATE["engine"]
    return {
        "ready": STATE["ready"],
        "device": (eng.device.upper() if eng else None),
        "mode": settings.MODE,
        "exercises": [e.name for e in EXERCISES.values()],
    }


app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Serves the website itself (keep this mount last: routes after it would be hidden)
if settings.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")
