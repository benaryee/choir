"""Pipeline orchestrator.

Drives a job through every stage, persisting status after each step so the
frontend can poll progress:

    UPLOADING -> PROCESSING -> READING_SCORE -> (NEEDS_REVIEW?) ->
    GENERATING_AUDIO -> READY

The OMR MusicXML is written to ``output/<job_id>/score.musicxml`` so the job can
be resumed after the user confirms/fixes voice labels in the correction UI.
"""
from __future__ import annotations

import traceback
from pathlib import Path

from ..config import get_settings
from ..jobs import get_job_store
from ..models import Job, JobStatus, OmrMethod, Stage, VoicePart
from ..storage import get_storage
from . import omr as omr_mod
from . import solfa as solfa_mod
from .parts import extract_parts
from .preprocess import preprocess_upload
from .synth import synthesize

CONTENT_TYPES = {
    ".png": "image/png",
    ".musicxml": "application/vnd.recordare.musicxml+xml",
    ".xml": "application/xml",
    ".mid": "audio/midi",
    ".mp3": "audio/mpeg",
    ".solfa": "text/plain; charset=utf-8",
    ".txt": "text/plain; charset=utf-8",
}


def _ct(path: Path) -> str:
    return CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")


def _set(job_id: str, **fields):
    def mutate(job: Job):
        for key, value in fields.items():
            setattr(job, key, value)
    return get_job_store().update(job_id, mutate)


def _job_output_dir(job_id: str) -> Path:
    out = get_settings().output_dir / job_id
    out.mkdir(parents=True, exist_ok=True)
    return out


def run_pipeline(job_id: str) -> None:
    """Run preprocessing + OMR. Stops at NEEDS_REVIEW when confidence is low."""
    settings = get_settings()
    store = get_job_store()
    storage = get_storage()
    job = store.get(job_id)
    if job is None:
        return

    # Tonic sol-fa text input skips OMR entirely: parse straight to MusicXML and
    # hand off to the shared extraction + synthesis stages.
    if solfa_mod.is_solfa_filename(job.filename):
        _run_solfa_input(job_id)
        return

    try:
        _set(job_id, status=JobStatus.RUNNING, stage=Stage.PROCESSING, progress=0.1)

        # --- Stage: pre-processing -------------------------------------------
        upload_path = settings.uploads_dir / job_id / job.filename
        work_dir = settings.pages_dir / job_id
        pages = preprocess_upload(upload_path, job.filename, work_dir)

        page_urls: list[str] = []
        for idx, page in enumerate(pages):
            key = f"{job_id}/pages/page_{idx + 1:03d}.png"
            page_urls.append(storage.save_file(key, page, _ct(page)))
        _set(job_id, page_count=len(pages), page_image_urls=page_urls, progress=1.0)

        # --- Stage: OMR -> MusicXML ------------------------------------------
        _set(job_id, stage=Stage.READING_SCORE, progress=0.2)
        omr_result = omr_mod.run_omr(pages, settings)

        out_dir = _job_output_dir(job_id)
        score_path = out_dir / "score.musicxml"
        score_path.write_text(omr_result.musicxml, encoding="utf-8")
        score_key = f"{job_id}/score.musicxml"
        score_url = storage.save_file(score_key, score_path, _ct(score_path))

        def apply_omr(j: Job):
            j.omr_method = omr_result.method
            j.omr_confidence = omr_result.confidence
            j.result.musicxml_url = score_url
            j.progress = 1.0
        store.update(job_id, apply_omr)

        # Low confidence -> hand off to the manual correction UI and pause.
        if (
            omr_result.method != OmrMethod.SAMPLE
            and omr_result.confidence < settings.omr_manual_threshold
        ):
            # Provide detected parts so the UI can show overlays for confirmation.
            extracted = extract_parts(omr_result.musicxml, out_dir)
            _set(
                job_id,
                status=JobStatus.NEEDS_REVIEW,
                detected_parts=extracted.detected,
            )
            return

        _finish_extraction_and_audio(job_id)

    except Exception as exc:  # noqa: BLE001 - surface any stage failure to the UI
        _set(
            job_id,
            status=JobStatus.FAILED,
            error=f"{exc}\n{traceback.format_exc()}",
        )


def _run_solfa_input(job_id: str) -> None:
    """Render an uploaded tonic sol-fa file into a score, then synth + finish."""
    settings = get_settings()
    store = get_job_store()
    storage = get_storage()
    job = store.get(job_id)
    if job is None:
        return
    try:
        _set(job_id, status=JobStatus.RUNNING, stage=Stage.READING_SCORE, progress=0.3)

        text = (settings.uploads_dir / job_id / job.filename).read_text(
            encoding="utf-8", errors="ignore"
        )
        musicxml = solfa_mod.solfa_to_musicxml(text)

        out_dir = _job_output_dir(job_id)
        score_path = out_dir / "score.musicxml"
        score_path.write_text(musicxml, encoding="utf-8")
        score_url = storage.save_file(
            f"{job_id}/score.musicxml", score_path, _ct(score_path)
        )

        def apply(j: Job):
            j.omr_method = OmrMethod.SOLFA
            j.omr_confidence = 1.0
            j.result.musicxml_url = score_url
            j.progress = 1.0
        store.update(job_id, apply)

        _finish_extraction_and_audio(job_id)
    except Exception as exc:  # noqa: BLE001
        _set(
            job_id,
            status=JobStatus.FAILED,
            error=f"{exc}\n{traceback.format_exc()}",
        )


def resume_after_correction(job_id: str, voice_by_part: dict[str, VoicePart]) -> None:
    """Re-run extraction using user-confirmed voice labels, then synth + finish."""
    store = get_job_store()
    job = store.get(job_id)
    if job is None:
        return
    try:
        _set(job_id, status=JobStatus.RUNNING, stage=Stage.READING_SCORE, progress=1.0)
        _finish_extraction_and_audio(job_id, voice_overrides=voice_by_part)
    except Exception as exc:  # noqa: BLE001
        _set(
            job_id,
            status=JobStatus.FAILED,
            error=f"{exc}\n{traceback.format_exc()}",
        )


def _finish_extraction_and_audio(
    job_id: str, voice_overrides: dict[str, VoicePart] | None = None
) -> None:
    settings = get_settings()
    store = get_job_store()
    storage = get_storage()
    out_dir = _job_output_dir(job_id)
    musicxml = (out_dir / "score.musicxml").read_text(encoding="utf-8")

    # --- Stage: part extraction ---------------------------------------------
    extracted = extract_parts(musicxml, out_dir)

    if voice_overrides:
        # Re-key MIDI/MusicXML maps according to user-confirmed labels.
        extracted = _apply_overrides(musicxml, out_dir, voice_overrides)

    # Persist per-voice MusicXML.
    for voice, path in extracted.musicxml_paths.items():
        storage.save_file(f"{job_id}/parts/{path.name}", path, _ct(path))

    # --- Stage: audio synthesis ---------------------------------------------
    _set(job_id, stage=Stage.GENERATING_AUDIO, progress=0.2)
    mp3s = synthesize(extracted.midi_paths, out_dir / "audio", settings)
    audio_urls: dict[str, str] = {}
    for voice, mp3 in mp3s.items():
        audio_urls[voice.value] = storage.save_file(
            f"{job_id}/audio/{mp3.name}", mp3, _ct(mp3)
        )

    # --- Tonic sol-fa generation --------------------------------------------
    solfa_urls, solfa_combined_url = _generate_solfa(job_id, musicxml, out_dir)

    def finalize(j: Job):
        j.result.audio = audio_urls
        j.result.solfa = solfa_urls
        j.result.solfa_combined_url = solfa_combined_url
        j.detected_parts = extracted.detected
        j.stage = Stage.READY
        j.status = JobStatus.SUCCEEDED
        j.progress = 1.0
    store.update(job_id, finalize)


def _generate_solfa(
    job_id: str, musicxml: str, out_dir: Path
) -> tuple[dict[str, str], str | None]:
    """Render per-voice + combined tonic sol-fa and store it. Best-effort."""
    storage = get_storage()
    try:
        by_voice, key_name = solfa_mod.score_to_solfa(musicxml)
    except Exception:  # noqa: BLE001 - sol-fa is a nice-to-have, never fail the job
        return {}, None
    if not by_voice:
        return {}, None

    solfa_dir = out_dir / "solfa"
    solfa_dir.mkdir(parents=True, exist_ok=True)

    solfa_urls: dict[str, str] = {}
    for voice, text in by_voice.items():
        path = solfa_dir / f"part_{voice.value}.solfa"
        path.write_text(f"key: {key_name}\n\n{voice.value}: {text}\n", encoding="utf-8")
        solfa_urls[voice.value] = storage.save_file(
            f"{job_id}/solfa/{path.name}", path, _ct(path)
        )

    combined_path = solfa_dir / "score.solfa"
    combined_path.write_text(
        solfa_mod.combined_solfa_text(by_voice, key_name), encoding="utf-8"
    )
    combined_url = storage.save_file(
        f"{job_id}/solfa/{combined_path.name}", combined_path, _ct(combined_path)
    )
    return solfa_urls, combined_url


def _apply_overrides(
    musicxml: str, out_dir: Path, overrides: dict[str, VoicePart]
):
    """Re-extract parts honouring user-confirmed ``part_id -> voice`` mapping."""
    from music21 import converter, midi

    from .parts import ExtractedParts

    score = converter.parseData(musicxml, format="musicxml")
    parts = list(score.parts) if hasattr(score, "parts") else []
    result = ExtractedParts()

    from music21 import stream

    full_score = stream.Score()
    for idx, part in enumerate(parts):
        voice = overrides.get(f"p{idx}")
        if voice is None or voice == VoicePart.FULL:
            continue
        full_score.insert(0, part)

        xml_path = out_dir / f"part_{voice.value}.musicxml"
        part.write("musicxml", fp=str(xml_path))
        result.musicxml_paths[voice] = xml_path

        midi_path = out_dir / f"part_{voice.value}.mid"
        mf = midi.translate.streamToMidiFile(part)
        mf.open(str(midi_path), "wb")
        mf.write()
        mf.close()
        result.midi_paths[voice] = midi_path

    if len(full_score.parts) > 0:
        full_midi = out_dir / "part_full.mid"
        mf = midi.translate.streamToMidiFile(full_score)
        mf.open(str(full_midi), "wb")
        mf.write()
        mf.close()
        result.midi_paths[VoicePart.FULL] = full_midi

    return result
