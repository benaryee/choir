"""Dispatch pipeline jobs either to Celery or an in-process thread pool.

This keeps the API endpoint identical regardless of execution backend: the
upload handler always calls :func:`enqueue` and returns immediately.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from .config import get_settings

_executor: ThreadPoolExecutor | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    if _executor is None:
        _executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")
    return _executor


def enqueue(job_id: str) -> None:
    """Schedule the OMR pipeline for ``job_id`` without blocking the request."""
    settings = get_settings()
    if settings.use_celery:
        from .celery_app import run_pipeline_task

        run_pipeline_task.delay(job_id)
    else:
        from .pipeline.runner import run_pipeline

        _get_executor().submit(run_pipeline, job_id)
