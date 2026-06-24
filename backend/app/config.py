"""Application configuration loaded from environment / .env."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # General
    data_dir: Path = Path("./data")
    public_base_url: str = "http://localhost:8000"

    # Job queue
    use_celery: bool = False
    celery_broker_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # Storage
    storage_backend: str = "local"  # "local" | "s3"
    s3_bucket: str = "choirparts"
    s3_region: str = "us-east-1"
    aws_access_key_id: str = ""
    aws_secret_access_key: str = ""
    s3_endpoint_url: str = ""

    # OMR: Audiveris
    audiveris_cmd: str = ""
    # A successful Audiveris transcription parses to ~0.6; keep the trust
    # threshold below that so we don't fall through to the weaker Vision model.
    omr_confidence_threshold: float = 0.5
    omr_manual_threshold: float = 0.4

    # OMR: GPT-4o Vision
    openai_api_key: str = ""
    openai_vision_model: str = "gpt-4o"

    # Audio synthesis
    soundfont_path: str = ""
    fluidsynth_cmd: str = "fluidsynth"
    ffmpeg_cmd: str = "ffmpeg"

    @property
    def uploads_dir(self) -> Path:
        return self.data_dir / "uploads"

    @property
    def pages_dir(self) -> Path:
        return self.data_dir / "pages"

    @property
    def output_dir(self) -> Path:
        return self.data_dir / "output"

    def ensure_dirs(self) -> None:
        for d in (self.data_dir, self.uploads_dir, self.pages_dir, self.output_dir):
            d.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
