"""Storage abstraction with an S3 backend and a local-filesystem fallback.

Originals, page images and rendered outputs are written through this layer so
the rest of the pipeline does not care whether it is talking to S3 or disk.
"""
from __future__ import annotations

import shutil
from abc import ABC, abstractmethod
from pathlib import Path

from .config import Settings, get_settings


class Storage(ABC):
    @abstractmethod
    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        """Persist raw bytes under ``key`` and return a retrievable URL."""

    @abstractmethod
    def save_file(self, key: str, path: Path, content_type: str = "application/octet-stream") -> str:
        """Persist a file under ``key`` and return a retrievable URL."""

    @abstractmethod
    def url_for(self, key: str) -> str:
        ...


class LocalStorage(Storage):
    """Writes objects under ``data_dir/store`` and serves them via the API."""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.data_dir / "store"
        self.root.mkdir(parents=True, exist_ok=True)

    def _dest(self, key: str) -> Path:
        dest = self.root / key
        dest.parent.mkdir(parents=True, exist_ok=True)
        return dest

    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self._dest(key).write_bytes(data)
        return self.url_for(key)

    def save_file(self, key: str, path: Path, content_type: str = "application/octet-stream") -> str:
        shutil.copyfile(path, self._dest(key))
        return self.url_for(key)

    def url_for(self, key: str) -> str:
        base = self.settings.public_base_url.rstrip("/")
        return f"{base}/files/{key}"

    def local_path(self, key: str) -> Path:
        return self.root / key


class S3Storage(Storage):
    def __init__(self, settings: Settings):
        import boto3  # imported lazily so local dev needs no AWS deps configured

        self.settings = settings
        self.bucket = settings.s3_bucket
        session_kwargs = {"region_name": settings.s3_region}
        if settings.aws_access_key_id and settings.aws_secret_access_key:
            session_kwargs.update(
                aws_access_key_id=settings.aws_access_key_id,
                aws_secret_access_key=settings.aws_secret_access_key,
            )
        client_kwargs = dict(session_kwargs)
        if settings.s3_endpoint_url:
            client_kwargs["endpoint_url"] = settings.s3_endpoint_url
        self.client = boto3.client("s3", **client_kwargs)

    def save_bytes(self, key: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=content_type)
        return self.url_for(key)

    def save_file(self, key: str, path: Path, content_type: str = "application/octet-stream") -> str:
        self.client.upload_file(
            str(path), self.bucket, key, ExtraArgs={"ContentType": content_type}
        )
        return self.url_for(key)

    def url_for(self, key: str) -> str:
        if self.settings.s3_endpoint_url:
            base = self.settings.s3_endpoint_url.rstrip("/")
            return f"{base}/{self.bucket}/{key}"
        return f"https://{self.bucket}.s3.{self.settings.s3_region}.amazonaws.com/{key}"


_storage: Storage | None = None


def get_storage() -> Storage:
    global _storage
    if _storage is None:
        settings = get_settings()
        if settings.storage_backend == "s3":
            _storage = S3Storage(settings)
        else:
            _storage = LocalStorage(settings)
    return _storage
