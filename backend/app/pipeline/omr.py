"""Stage 2 - Optical Music Recognition.

Strategy:
    1. Primary: self-hosted Audiveris (Java) -> MusicXML + a confidence score.
    2. Fallback: if confidence < ``OMR_CONFIDENCE_THRESHOLD``, call GPT-4o Vision.
    3. If confidence is still below ``OMR_MANUAL_THRESHOLD``, the runner surfaces
       the manual-correction UI.
    4. Local-dev safety net: if neither engine is configured, emit a sample SATB
       score so the rest of the pipeline can be exercised end to end.

Each engine returns an :class:`OmrResult` (MusicXML text + confidence + method).
"""
from __future__ import annotations

import base64
import logging
import re
import subprocess
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from ..models import OmrMethod
from .sample import sample_satb_musicxml

logger = logging.getLogger(__name__)

GPT4O_PROMPT = (
    "This is a page of choral sheet music. Please output a valid MusicXML "
    "representation of all voice parts (Soprano, Alto, Tenor, Bass) that you "
    "can identify. Return only the MusicXML XML, nothing else."
)


@dataclass
class OmrResult:
    musicxml: str
    confidence: float
    method: OmrMethod


def _read_musicxml_from_output(out_dir: Path) -> str | None:
    """Audiveris writes either a .mxl (zip) or .musicxml file; read whichever."""
    for mxl in sorted(out_dir.glob("**/*.mxl")):
        with zipfile.ZipFile(mxl) as zf:
            for name in zf.namelist():
                if name.endswith((".xml", ".musicxml")) and "META-INF" not in name:
                    return zf.read(name).decode("utf-8")
    for xml in sorted(out_dir.glob("**/*.musicxml")) + sorted(out_dir.glob("**/*.xml")):
        return xml.read_text(encoding="utf-8")
    return None


def run_audiveris(image_paths: list[Path], settings: Settings) -> OmrResult | None:
    """Invoke the Audiveris CLI in batch mode to export MusicXML."""
    if not settings.audiveris_cmd:
        return None

    with tempfile.TemporaryDirectory() as tmp:
        out_dir = Path(tmp)
        # Audiveris 5.3 CLI: options first, then "--" separator, then inputs.
        cmd = [
            settings.audiveris_cmd,
            "-batch",
            "-export",
            "-output", str(out_dir),
            "--",
            *[str(p) for p in image_paths],
        ]
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, check=False
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            # Misconfigured AUDIVERIS_CMD (missing/dir/not executable), launch
            # timeout, etc. Don't fail the job - fall back to the next engine.
            logger.warning("Audiveris launch failed (%s): %s", settings.audiveris_cmd, exc)
            return None

        musicxml = _read_musicxml_from_output(out_dir)
        if not musicxml:
            return None
        confidence = _parse_audiveris_confidence(proc.stdout + proc.stderr)
        return OmrResult(musicxml=musicxml, confidence=confidence, method=OmrMethod.AUDIVERIS)


def _parse_audiveris_confidence(log_text: str) -> float:
    """Best-effort extraction of a 0..1 confidence from Audiveris logs."""
    matches = re.findall(r"(?:grade|confidence)[^0-9]*([01]?\.\d+)", log_text, re.I)
    if not matches:
        # No explicit grade reported; assume a usable-but-unverified result.
        return 0.6
    vals = [float(m) for m in matches]
    return max(0.0, min(1.0, sum(vals) / len(vals)))


def _strip_code_fence(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n", "", text)
        text = re.sub(r"\n```$", "", text)
    return text.strip()


def run_gpt4o_vision(image_paths: list[Path], settings: Settings) -> OmrResult | None:
    """Send page images to GPT-4o Vision and parse the returned MusicXML."""
    if not settings.openai_api_key:
        return None
    try:
        from openai import OpenAI
    except ImportError:
        return None

    try:
        client = OpenAI(api_key=settings.openai_api_key)
    except Exception as exc:
        # e.g. SDK/httpx version mismatch; fall back instead of failing the job.
        logger.warning("OpenAI client init failed: %s", exc)
        return None

    content: list[dict] = [{"type": "text", "text": GPT4O_PROMPT}]
    for path in image_paths:
        b64 = base64.b64encode(path.read_bytes()).decode("ascii")
        content.append(
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/png;base64,{b64}"},
            }
        )

    try:
        resp = client.chat.completions.create(
            model=settings.openai_vision_model,
            messages=[{"role": "user", "content": content}],
            temperature=0,
        )
    except Exception:
        return None

    raw = resp.choices[0].message.content or ""
    musicxml = _strip_code_fence(raw)
    if "<score-partwise" not in musicxml and "<score-timewise" not in musicxml:
        return None
    # Vision output is plausible but unverified; keep below the Audiveris band so
    # the runner still recommends a manual review.
    return OmrResult(musicxml=musicxml, confidence=0.55, method=OmrMethod.GPT4O_VISION)


def run_omr(image_paths: list[Path], settings: Settings) -> OmrResult:
    """Execute the OMR cascade and return the best available result."""
    result = run_audiveris(image_paths, settings)
    if result and result.confidence >= settings.omr_confidence_threshold:
        return result

    fallback = run_gpt4o_vision(image_paths, settings)
    if fallback is not None:
        # Prefer whichever engine reported higher confidence.
        if result is None or fallback.confidence >= result.confidence:
            result = fallback

    if result is not None:
        return result

    # Nothing configured -> deterministic sample so the pipeline still completes.
    return OmrResult(
        musicxml=sample_satb_musicxml(), confidence=1.0, method=OmrMethod.SAMPLE
    )
