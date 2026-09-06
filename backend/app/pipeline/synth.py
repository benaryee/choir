"""Stage 4 - audio synthesis.

Renders each part MIDI to WAV with FluidSynth + a choral soundfont, then
encodes to MP3 with ffmpeg. Produces soprano/alto/tenor/bass/full MP3s.

Three things matter for a usable practice track, and each shapes this module:

* **Timbre** - the parts carry a sung GM patch (set in ``parts.py``), not the
  Acoustic Grand Piano that an instrument-less Audiveris export defaults to.
* **Separation** - the full mix is built by panning the individually rendered
  voices across the stereo field rather than synthesising the merged MIDI, so a
  singer can pick their line out of the texture. This is also *cheaper*: it
  reuses audio we already rendered instead of running a fifth FluidSynth pass.
* **Level** - every track is loudness-normalised to the same target, so
  switching parts in the player doesn't jump in volume.

Voices are rendered concurrently; FluidSynth and ffmpeg are separate processes,
so the work overlaps despite the GIL.

If no soundfont is configured this stage is skipped gracefully so the core
upload -> OMR -> MusicXML milestone still completes.
"""
from __future__ import annotations

import logging
import math
import shutil
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

from ..config import Settings
from ..models import VoicePart

logger = logging.getLogger(__name__)

# Stereo placement for the full mix, in [-1, 1] (left to right), following a
# conventional choir layout as heard from the audience.
_PAN_POSITION: dict[VoicePart, float] = {
    VoicePart.SOPRANO: -0.6,
    VoicePart.ALTO: -0.2,
    VoicePart.TENOR: 0.2,
    VoicePart.BASS: 0.6,
}

# Per-voice attenuation applied before summing, so four simultaneous voices
# don't drive the mix bus into clipping ahead of the normaliser.
_MIX_VOICE_GAIN = 0.6

ProgressCb = Callable[[float], None]


def synthesis_available(settings: Settings) -> bool:
    return bool(
        settings.soundfont_path
        and Path(settings.soundfont_path).exists()
        and shutil.which(settings.fluidsynth_cmd)
        and shutil.which(settings.ffmpeg_cmd)
    )


def _constant_power_gains(position: float) -> tuple[float, float]:
    """Left/right gains for a pan position, keeping perceived level constant.

    Linear panning dips ~3dB in the middle of the field; the sine/cosine law
    used here keeps a centre-panned voice as loud as a hard-panned one.
    """
    clamped = max(-1.0, min(1.0, position))
    return math.sqrt((1.0 - clamped) / 2.0), math.sqrt((1.0 + clamped) / 2.0)


def _loudnorm_filter(settings: Settings) -> str:
    return f"loudnorm=I={settings.loudness_target_lufs}:TP=-1.5:LRA=11"


def _midi_to_wav(midi_path: Path, wav_path: Path, settings: Settings) -> None:
    subprocess.run(
        [
            settings.fluidsynth_cmd,
            "-ni",
            "-F", str(wav_path),
            "-r", "44100",
            "-g", str(settings.fluidsynth_gain),
            # A little reverb gives the voices space; chorus is left off because
            # it smears pitch, which is the opposite of what a practice track needs.
            "-R", "1",
            "-C", "0",
            settings.soundfont_path,
            str(midi_path),
        ],
        check=True,
        capture_output=True,
    )


def _wav_to_mp3(wav_path: Path, mp3_path: Path, settings: Settings) -> None:
    filters = ["aformat=channel_layouts=stereo"]
    if settings.normalize_audio:
        filters.append(_loudnorm_filter(settings))
    subprocess.run(
        [
            settings.ffmpeg_cmd,
            "-y",
            "-i", str(wav_path),
            "-filter:a", ",".join(filters),
            "-codec:a", "libmp3lame",
            "-qscale:a", "2",
            "-ar", "44100",
            str(mp3_path),
        ],
        check=True,
        capture_output=True,
    )


def _mix_full(
    voice_wavs: dict[VoicePart, Path], mp3_path: Path, settings: Settings
) -> bool:
    """Pan the rendered voices across the stereo field and encode the mix."""
    voices = [v for v in _PAN_POSITION if v in voice_wavs]
    if len(voices) < 2:
        return False

    cmd = [settings.ffmpeg_cmd, "-y"]
    for voice in voices:
        cmd += ["-i", str(voice_wavs[voice])]

    chains = []
    for idx, voice in enumerate(voices):
        left, right = _constant_power_gains(_PAN_POSITION[voice])
        chains.append(
            f"[{idx}:a]aformat=channel_layouts=mono,"
            f"pan=stereo|c0={left * _MIX_VOICE_GAIN:.4f}*c0"
            f"|c1={right * _MIX_VOICE_GAIN:.4f}*c0[v{idx}]"
        )
    labels = "".join(f"[v{i}]" for i in range(len(voices)))
    # normalize=0: amix would otherwise divide by the input count and make the
    # mix quieter as more voices are found. Level is set by the normaliser below.
    mix = f"{labels}amix=inputs={len(voices)}:normalize=0"
    if settings.normalize_audio:
        mix += f",{_loudnorm_filter(settings)}"
    chains.append(f"{mix}[out]")

    cmd += [
        "-filter_complex", ";".join(chains),
        "-map", "[out]",
        "-codec:a", "libmp3lame",
        "-qscale:a", "2",
        "-ar", "44100",
        str(mp3_path),
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True)
    except subprocess.CalledProcessError as exc:
        logger.warning("full-mix render failed: %s", exc.stderr[-500:] if exc.stderr else exc)
        return False
    return True


def synthesize(
    midi_paths: dict[VoicePart, Path],
    out_dir: Path,
    settings: Settings,
    progress_cb: ProgressCb | None = None,
) -> dict[VoicePart, Path]:
    """Render every voice MIDI to an MP3. Returns voice -> mp3 path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[VoicePart, Path] = {}
    if not synthesis_available(settings):
        return results

    # The merged MIDI is rendered only as a fallback; normally the full mix is
    # built from the individual voices further down.
    single_voices = [v for v in midi_paths if v != VoicePart.FULL]
    voice_wavs: dict[VoicePart, Path] = {}
    done = 0

    def render(voice: VoicePart) -> tuple[VoicePart, Path, Path] | None:
        wav_path = out_dir / f"{voice.value}.wav"
        mp3_path = out_dir / f"{voice.value}.mp3"
        try:
            _midi_to_wav(midi_paths[voice], wav_path, settings)
            _wav_to_mp3(wav_path, mp3_path, settings)
        except subprocess.CalledProcessError as exc:
            logger.warning("render failed for %s: %s", voice.value, exc)
            wav_path.unlink(missing_ok=True)
            return None
        return voice, mp3_path, wav_path

    workers = max(1, min(settings.synth_workers, len(single_voices) or 1))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for outcome in pool.map(render, single_voices):
            done += 1
            if progress_cb:
                # Leave the last slice of the bar for the full mix.
                progress_cb(0.2 + 0.6 * (done / max(1, len(single_voices))))
            if outcome is None:
                continue
            voice, mp3_path, wav_path = outcome
            results[voice] = mp3_path
            voice_wavs[voice] = wav_path

    try:
        full_mp3 = out_dir / f"{VoicePart.FULL.value}.mp3"
        if _mix_full(voice_wavs, full_mp3, settings):
            results[VoicePart.FULL] = full_mp3
        elif VoicePart.FULL in midi_paths:
            # Fewer than two voices to mix (or the mix failed): fall back to
            # synthesising the merged MIDI directly.
            outcome = render(VoicePart.FULL)
            if outcome is not None:
                results[VoicePart.FULL] = outcome[1]
                outcome[2].unlink(missing_ok=True)
    finally:
        for wav_path in voice_wavs.values():
            wav_path.unlink(missing_ok=True)

    if progress_cb:
        progress_cb(1.0)
    return results
