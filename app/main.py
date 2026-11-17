"""Transcryber — a local audio transcription web app with user accounts."""

import logging
import os
import secrets
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from . import config, storage
from .auth import authenticate, current_user, seed_users
from .config import DATA_DIR
from .db import init_db
from .transcribe import UnsupportedMediaError, get_model_info, transcribe_file

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("transcryber")

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = DATA_DIR / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

SECRET_KEY = config.SECRET_KEY
if not SECRET_KEY:
    SECRET_KEY = secrets.token_hex(32)
    logger.warning(
        "secret_key not set in config — generated a temporary one; all logins "
        "reset on restart. Set secret_key in config.yaml to keep sessions valid."
    )

app = FastAPI(title="Transcryber")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY, same_site="lax")


@app.on_event("startup")
def _startup():
    init_db()
    seed_users(config.USERS)


# One worker: process a single file at a time so a low-resource box isn't swamped.
executor = ThreadPoolExecutor(max_workers=1)
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()


def _run_job(job_id: str, audio_path: str, original_name: str, user_id: int) -> None:
    with jobs_lock:
        jobs[job_id]["status"] = "processing"
    logger.info("Job %s: transcribing '%s'…", job_id, original_name)
    started = time.monotonic()
    try:
        result = transcribe_file(audio_path)
        # From start of processing to transcript ready; excludes queue wait.
        processing_seconds = round(time.monotonic() - started, 2)
        logger.info(
            "Job %s: done — %s, %.1fs of audio, %d chars, took %.1fs.",
            job_id,
            result["language"],
            result["duration"],
            len(result["text"]),
            processing_seconds,
        )
        record = storage.save_transcript(
            user_id=user_id,
            original_name=original_name,
            text=result["text"],
            language=result["language"],
            duration=result["duration"],
            segments=result["segments"],
            processing_seconds=processing_seconds,
        )
        with jobs_lock:
            jobs[job_id].update(status="done", transcript_id=record["id"])
    except UnsupportedMediaError as exc:
        # Expected user error (e.g. a video with no sound): no stack trace.
        logger.info("Job %s: rejected — %s", job_id, exc)
        with jobs_lock:
            jobs[job_id].update(status="error", error=str(exc))
    except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
        logger.exception("Job %s: failed — %s", job_id, exc)
        with jobs_lock:
            jobs[job_id].update(status="error", error=str(exc))
    finally:
        try:
            os.remove(audio_path)
        except OSError:
            pass


# ---- Auth routes -------------------------------------------------------
@app.post("/api/login")
async def login(request: Request):
    body = await request.json()
    user = authenticate(body.get("username", ""), body.get("password", ""))
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    request.session["user_id"] = user["id"]
    logger.info("User '%s' logged in.", user["username"])
    return {"username": user["username"]}


@app.post("/api/logout")
async def logout(request: Request):
    request.session.clear()
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(current_user)):
    return {"username": user["username"]}


# ---- Transcription routes (all owner-scoped) ---------------------------
@app.post("/api/transcribe")
async def create_transcription(
    file: UploadFile = File(...), user: dict = Depends(current_user)
):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    job_id = uuid.uuid4().hex
    ext = Path(file.filename).suffix
    audio_path = UPLOAD_DIR / f"{job_id}{ext}"

    with open(audio_path, "wb") as f:
        while chunk := await file.read(1024 * 1024):
            f.write(chunk)

    with jobs_lock:
        jobs[job_id] = {"status": "queued", "filename": file.filename, "user_id": user["id"]}
    executor.submit(_run_job, job_id, str(audio_path), file.filename, user["id"])

    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str, user: dict = Depends(current_user)):
    with jobs_lock:
        job = jobs.get(job_id)
    if not job or job.get("user_id") != user["id"]:
        raise HTTPException(status_code=404, detail="Job not found")
    return {"job_id": job_id, **{k: v for k, v in job.items() if k != "user_id"}}


@app.get("/api/transcripts")
def list_transcripts(user: dict = Depends(current_user)):
    return storage.list_transcripts(user["id"])


@app.get("/api/transcripts/{tid}")
def get_transcript(tid: str, user: dict = Depends(current_user)):
    rec = storage.load_transcript(user["id"], tid)
    if not rec:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return rec


@app.delete("/api/transcripts/{tid}")
def delete_transcript(tid: str, user: dict = Depends(current_user)):
    if not storage.delete_transcript(user["id"], tid):
        raise HTTPException(status_code=404, detail="Transcript not found")
    return {"deleted": tid}


@app.get("/api/transcripts/{tid}/download")
def download_transcript(tid: str, user: dict = Depends(current_user)):
    rec = storage.load_transcript(user["id"], tid)
    if not rec:
        raise HTTPException(status_code=404, detail="Transcript not found")
    stem = Path(rec.get("original_name") or tid).stem
    return PlainTextResponse(
        rec["text"],
        headers={"Content-Disposition": f'attachment; filename="{stem}.txt"'},
    )


@app.get("/api/status")
def status(user: dict = Depends(current_user)):
    return get_model_info()


app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


@app.get("/", response_class=HTMLResponse)
def index():
    return (BASE_DIR / "static" / "index.html").read_text(encoding="utf-8")
