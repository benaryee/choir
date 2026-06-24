"""ChoirParts FastAPI application.

Endpoints:
    POST /api/upload                 - accept a PDF/image, enqueue the pipeline.
    GET  /api/jobs/{job_id}          - poll job status / stage / results.
    POST /api/jobs/{job_id}/corrections - submit manual voice-label fixes.
    GET  /files/{key}                - serve locally-stored artefacts (dev).
"""
from __future__ import annotations

import uuid
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .config import get_settings
from .jobs import get_job_store
from .models import (
    STAGE_ORDER,
    CorrectionRequest,
    Job,
    JobStatus,
    Stage,
    UploadResponse,
)
from .queue import enqueue
from .storage import LocalStorage, get_storage

settings = get_settings()

app = FastAPI(title="ChoirParts API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ALLOWED_SUFFIXES = {
    ".pdf", ".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp",
    ".sol", ".solfa", ".txt",  # tonic sol-fa text input
}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "stages": [s.value for s in STAGE_ORDER]}


@app.post("/api/upload", response_model=UploadResponse)
async def upload(file: UploadFile = File(...)) -> UploadResponse:
    filename = file.filename or "upload"
    suffix = Path(filename).suffix.lower()
    if suffix not in ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix}'. Allowed: {sorted(ALLOWED_SUFFIXES)}",
        )

    job_id = uuid.uuid4().hex
    job_upload_dir = settings.uploads_dir / job_id
    job_upload_dir.mkdir(parents=True, exist_ok=True)
    dest = job_upload_dir / filename

    data = await file.read()
    dest.write_bytes(data)

    # Store the original through the storage layer (S3 in prod, disk in dev).
    storage = get_storage()
    storage.save_file(f"{job_id}/original/{filename}", dest)

    store = get_job_store()
    job = Job(
        id=job_id,
        status=JobStatus.QUEUED,
        stage=Stage.UPLOADING,
        filename=filename,
        progress=1.0,
    )
    store.create(job)

    enqueue(job_id)
    return UploadResponse(job_id=job_id, status=job.status, stage=job.stage)


@app.get("/api/jobs/{job_id}", response_model=Job)
def get_job(job_id: str) -> Job:
    job = get_job_store().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@app.post("/api/jobs/{job_id}/corrections", response_model=Job)
def submit_corrections(job_id: str, body: CorrectionRequest) -> Job:
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.status != JobStatus.NEEDS_REVIEW:
        raise HTTPException(
            status_code=409, detail="Job is not awaiting manual correction"
        )

    voice_by_part = {c.part_id: c.voice for c in body.corrections}

    # Resume the pipeline asynchronously with the confirmed labels.
    from .config import get_settings as _gs

    if _gs().use_celery:
        from .celery_app import celery

        celery.send_task(
            "choirparts.resume_pipeline",
            args=[job_id, {pid: v.value for pid, v in voice_by_part.items()}],
        )
    else:
        from concurrent.futures import ThreadPoolExecutor

        from .pipeline.runner import resume_after_correction

        ThreadPoolExecutor(max_workers=1).submit(
            resume_after_correction, job_id, voice_by_part
        )

    updated = store.update(job_id, lambda j: setattr(j, "status", JobStatus.RUNNING))
    return updated or job


@app.get("/files/{key:path}")
def serve_file(key: str) -> FileResponse:
    storage = get_storage()
    if not isinstance(storage, LocalStorage):
        raise HTTPException(status_code=404, detail="File serving disabled for S3 backend")
    path = storage.local_path(key)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path)
