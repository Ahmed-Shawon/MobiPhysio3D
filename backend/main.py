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
    GET  /api/report/{job_id}.pdf   PDF report of a finished analysis (guests too)

Accounts (cookie login, see accounts.py):
    POST /api/auth/signup | /api/auth/login | /api/auth/logout,  GET /api/auth/me
    GET  /api/assessments            the logged-in user's saved results
    GET  /api/assessments.csv        same, as CSV
    GET  /api/assessments/{id}       one result;  DELETE removes it
    GET  /api/assessments/{id}/skeleton.gif | /report.pdf
"""
import asyncio
import csv
import io
import logging
import shutil
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime

from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import accounts
import report
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

    accounts.init()
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


def current_user(request: Request):
    return accounts.user_for_token(request.cookies.get(settings.SESSION_COOKIE))


def require_user(request: Request):
    user = current_user(request)
    if user is None:
        raise UserError(401, "Log in to see your saved assessments.")
    return user


@app.post("/api/analyze")
async def analyze(request: Request, video: Optional[UploadFile] = File(None),
                  exercise_id: Optional[str] = Form(None)):
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
        user = current_user(request)
        job_id, future = JOBS.submit(STATE["engine"], path, exercise_id,
                                     user_id=user["id"] if user else None,
                                     video_name=Path(video.filename).name[:200])
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


# ------------------------------------------------------------------ PDF report
def _pdf_response(pdf: bytes, exercise_id: str, created: float):
    name = (f"MobiPhysio_{EXERCISES[exercise_id].name.replace(' ', '_')}_"
            f"{datetime.fromtimestamp(created).strftime('%Y-%m-%d_%H%M')}.pdf")
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@app.get("/api/report/{job_id}.pdf")
async def job_report(job_id: str):
    job = JOBS.get(job_id)
    if job is None or job["status"] != "done":
        raise UserError(404, "This analysis was not found or has expired. Run it again to get a report.")
    r = job["result"]
    pdf = await run_in_threadpool(report.build, job["exercise"], r["score"], r["details"], job["created"],
                                  job.get("video_name"), job.get("keyframes") or [])
    return _pdf_response(pdf, job["exercise"], job["created"])


# ------------------------------------------------------------------ accounts
class SignUp(BaseModel):
    name: str = ""
    email: str = ""
    password: str = ""


class LogIn(BaseModel):
    email: str = ""
    password: str = ""


def _login_response(user):
    token = accounts.new_session(user["id"])
    res = JSONResponse({"user": user})
    res.set_cookie(settings.SESSION_COOKIE, token, max_age=int(settings.SESSION_DAYS * 86400),
                   httponly=True, samesite="lax", secure=settings.COOKIE_SECURE, path="/")
    return res


@app.post("/api/auth/signup")
async def signup(body: SignUp):
    user = await run_in_threadpool(accounts.create_user, body.name, body.email, body.password)
    log.info("New account %s", user["id"])
    return _login_response(user)


@app.post("/api/auth/login")
async def login(body: LogIn):
    user = await run_in_threadpool(accounts.authenticate, body.email, body.password)
    return _login_response(user)


@app.post("/api/auth/logout")
def logout(request: Request):
    accounts.end_session(request.cookies.get(settings.SESSION_COOKIE))
    res = JSONResponse({"ok": True})
    res.delete_cookie(settings.SESSION_COOKIE, path="/")
    return res


@app.get("/api/auth/me")
def me(request: Request):
    return {"user": current_user(request)}


def _assessment_out(a):
    ex = EXERCISES.get(a["exercise_id"])
    return {**a,
            "exercise_name": ex.name if ex else a["exercise_id"],
            "model": report.model_combo(ex) if ex else "",
            "skeleton_url": f"/api/assessments/{a['id']}/skeleton.gif",
            "report_url": f"/api/assessments/{a['id']}/report.pdf"}


@app.get("/api/assessments")
def my_assessments(request: Request):
    user = require_user(request)
    return {"assessments": [_assessment_out(a) for a in accounts.list_assessments(user["id"])]}


@app.get("/api/assessments.csv")
def my_assessments_csv(request: Request):
    user = require_user(request)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "time", "exercise", "score", "model", "video_file"])
    for a in accounts.list_assessments(user["id"]):
        ex = EXERCISES.get(a["exercise_id"])
        d = datetime.fromtimestamp(a["created"])
        w.writerow([d.strftime("%Y-%m-%d"), d.strftime("%H:%M"), ex.name if ex else a["exercise_id"],
                    f"{a['score']:.2f}", report.model_combo(ex) if ex else "", a["video_name"] or ""])
    # BOM so Excel opens it as UTF-8
    return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="MobiPhysio_history.csv"'})


@app.get("/api/assessments/{assessment_id}")
def one_assessment(assessment_id: int, request: Request):
    user = require_user(request)
    a, folder = accounts.get_assessment(user["id"], assessment_id)
    out = _assessment_out(a)
    out["keyframes"] = [f"/api/assessments/{assessment_id}/frame/{i}.jpg"
                        for i in range(len(accounts.saved_keyframes(folder)))]
    return out


@app.post("/api/assessments/claim/{job_id}")
async def claim_assessment(job_id: str, request: Request):
    """Saves a result that was made as a guest, right after the guest signs up or logs in."""
    user = require_user(request)
    job = JOBS.get(job_id)
    if job is None or job["status"] != "done":
        raise UserError(404, "This analysis was not found or has expired.")
    if job["result"].get("assessment_id"):
        return {"assessment_id": job["result"]["assessment_id"]}
    r = job["result"]
    aid = await run_in_threadpool(accounts.save_assessment, user["id"], job["exercise"], r["score"],
                                  r["details"], job.get("video_name"),
                                  settings.OUTPUT_DIR / f"{job_id}.gif", job.get("keyframes") or [])
    JOBS.mark_saved(job_id, aid)
    return {"assessment_id": aid}


@app.delete("/api/assessments/{assessment_id}")
def remove_assessment(assessment_id: int, request: Request):
    user = require_user(request)
    accounts.delete_assessment(user["id"], assessment_id)
    return {"ok": True}


@app.get("/api/assessments/{assessment_id}/skeleton.gif")
def saved_gif(assessment_id: int, request: Request):
    user = require_user(request)
    _, folder = accounts.get_assessment(user["id"], assessment_id)
    path = folder / "skeleton.gif"
    if not path.is_file():
        raise UserError(404, "The skeleton GIF for this assessment is missing.")
    return FileResponse(path, media_type="image/gif")


@app.get("/api/assessments/{assessment_id}/frame/{index}.jpg")
def saved_frame(assessment_id: int, index: int, request: Request):
    user = require_user(request)
    _, folder = accounts.get_assessment(user["id"], assessment_id)
    path = folder / f"input_{index}.jpg"
    if not (0 <= index < settings.KEYFRAMES) or not path.is_file():
        raise UserError(404, "This frame was not found.")
    return FileResponse(path, media_type="image/jpeg")


@app.get("/api/assessments/{assessment_id}/report.pdf")
async def saved_report(assessment_id: int, request: Request):
    user = require_user(request)
    a, folder = accounts.get_assessment(user["id"], assessment_id)
    pdf = await run_in_threadpool(report.build, a["exercise_id"], a["score"], a["details"], a["created"],
                                  a["video_name"], accounts.saved_keyframes(folder))
    return _pdf_response(pdf, a["exercise_id"], a["created"])


app.mount("/outputs", StaticFiles(directory=settings.OUTPUT_DIR), name="outputs")

# Serves the website itself (keep this mount last: routes after it would be hidden)
if settings.FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=settings.FRONTEND_DIR, html=True), name="frontend")
