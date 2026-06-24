"""Job store: keeps pipeline job state and makes it queryable for polling.

Two backends are provided:

* ``InMemoryJobStore`` - default; great for single-process dev (threaded queue).
* ``RedisJobStore`` - used when Celery is enabled so the API process and the
  worker process share state.
"""
from __future__ import annotations

import threading
from abc import ABC, abstractmethod
from typing import Callable, Optional

from .config import get_settings
from .models import Job


class JobStore(ABC):
    @abstractmethod
    def create(self, job: Job) -> None:
        ...

    @abstractmethod
    def get(self, job_id: str) -> Optional[Job]:
        ...

    @abstractmethod
    def save(self, job: Job) -> None:
        ...

    def update(self, job_id: str, mutate: Callable[[Job], None]) -> Optional[Job]:
        job = self.get(job_id)
        if job is None:
            return None
        mutate(job)
        job.touch()
        self.save(job)
        return job


class InMemoryJobStore(JobStore):
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()

    def create(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job.model_copy(deep=True)

    def get(self, job_id: str) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            return job.model_copy(deep=True) if job else None

    def save(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.id] = job.model_copy(deep=True)

    def update(self, job_id: str, mutate: Callable[[Job], None]) -> Optional[Job]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            mutate(job)
            job.touch()
            return job.model_copy(deep=True)


class RedisJobStore(JobStore):
    PREFIX = "choirparts:job:"

    def __init__(self, url: str) -> None:
        import redis  # lazy import

        self._r = redis.Redis.from_url(url)
        self._lock = threading.RLock()

    def _key(self, job_id: str) -> str:
        return f"{self.PREFIX}{job_id}"

    def create(self, job: Job) -> None:
        self.save(job)

    def get(self, job_id: str) -> Optional[Job]:
        raw = self._r.get(self._key(job_id))
        if raw is None:
            return None
        return Job.model_validate_json(raw)

    def save(self, job: Job) -> None:
        self._r.set(self._key(job.id), job.model_dump_json(), ex=60 * 60 * 24)

    def update(self, job_id: str, mutate: Callable[[Job], None]) -> Optional[Job]:
        # Best-effort atomicity via a short-lived distributed lock.
        with self._lock:
            job = self.get(job_id)
            if job is None:
                return None
            mutate(job)
            job.touch()
            self.save(job)
            return job


_store: JobStore | None = None


def get_job_store() -> JobStore:
    global _store
    if _store is None:
        settings = get_settings()
        if settings.use_celery:
            _store = RedisJobStore(settings.celery_result_backend)
        else:
            _store = InMemoryJobStore()
    return _store
