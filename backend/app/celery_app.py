"""Celery application + task definition for the OMR pipeline.

Only used when ``USE_CELERY=true``. Run a worker with::

    celery -A app.celery_app.celery worker --loglevel=info
"""
from __future__ import annotations

from celery import Celery

from .config import get_settings

settings = get_settings()

celery = Celery(
    "choirparts",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)


@celery.task(name="choirparts.run_pipeline")
def run_pipeline_task(job_id: str) -> str:
    # Imported here to avoid a circular import at module load time.
    from .pipeline.runner import run_pipeline

    run_pipeline(job_id)
    return job_id


@celery.task(name="choirparts.resume_pipeline")
def resume_pipeline_task(job_id: str, voice_by_part: dict[str, str]) -> str:
    from .models import VoicePart
    from .pipeline.runner import resume_after_correction

    overrides = {pid: VoicePart(v) for pid, v in voice_by_part.items()}
    resume_after_correction(job_id, overrides)
    return job_id
