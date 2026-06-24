"""Pydantic schemas and job-state data structures."""
from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class Stage(str, Enum):
    """Ordered pipeline stages surfaced to the UI progress bar."""

    UPLOADING = "uploading"
    PROCESSING = "processing"      # pre-processing: deskew/denoise/split
    READING_SCORE = "reading_score"  # OMR -> MusicXML
    GENERATING_AUDIO = "generating_audio"
    READY = "ready"


# Display order used by the frontend progress indicator.
STAGE_ORDER: list[Stage] = [
    Stage.UPLOADING,
    Stage.PROCESSING,
    Stage.READING_SCORE,
    Stage.GENERATING_AUDIO,
    Stage.READY,
]


class JobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_REVIEW = "needs_review"  # manual correction UI required
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class VoicePart(str, Enum):
    SOPRANO = "soprano"
    ALTO = "alto"
    TENOR = "tenor"
    BASS = "bass"
    FULL = "full"


class OmrMethod(str, Enum):
    AUDIVERIS = "audiveris"
    GPT4O_VISION = "gpt4o_vision"
    SAMPLE = "sample"
    SOLFA = "solfa"  # input was a tonic sol-fa file; no OMR needed


class DetectedPart(BaseModel):
    """A voice part detected during OMR, used by the manual correction UI."""

    id: str
    label: str                 # detected label e.g. "Soprano"
    suggested_voice: Optional[VoicePart] = None
    confidence: float = 0.0


class JobResult(BaseModel):
    musicxml_url: Optional[str] = None
    audio: dict[str, str] = Field(default_factory=dict)  # voice -> mp3 url
    solfa: dict[str, str] = Field(default_factory=dict)  # voice -> solfa text url
    solfa_combined_url: Optional[str] = None  # whole-piece labelled sol-fa


class Job(BaseModel):
    id: str
    status: JobStatus = JobStatus.QUEUED
    stage: Stage = Stage.UPLOADING
    progress: float = 0.0  # 0..1 within current stage
    filename: str = ""
    page_count: int = 0
    omr_method: Optional[OmrMethod] = None
    omr_confidence: Optional[float] = None
    detected_parts: list[DetectedPart] = Field(default_factory=list)
    page_image_urls: list[str] = Field(default_factory=list)
    result: JobResult = Field(default_factory=JobResult)
    error: Optional[str] = None
    created_at: float = Field(default_factory=time.time)
    updated_at: float = Field(default_factory=time.time)

    def touch(self) -> None:
        self.updated_at = time.time()


class UploadResponse(BaseModel):
    job_id: str
    status: JobStatus
    stage: Stage


class PartCorrection(BaseModel):
    part_id: str
    voice: VoicePart


class CorrectionRequest(BaseModel):
    corrections: list[PartCorrection]
