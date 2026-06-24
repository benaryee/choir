"""Stage 4 - audio synthesis.

Renders each part MIDI to WAV with FluidSynth + a choral soundfont, then
encodes to MP3 with ffmpeg. Produces soprano/alto/tenor/bass/full MP3s.

If no soundfont is configured this stage is skipped gracefully so the core
upload -> OMR -> MusicXML milestone still completes.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ..config import Settings
from ..models import VoicePart


def synthesis_available(settings: Settings) -> bool:
    return bool(
        settings.soundfont_path
        and Path(settings.soundfont_path).exists()
        and shutil.which(settings.fluidsynth_cmd)
        and shutil.which(settings.ffmpeg_cmd)
    )


def _midi_to_wav(midi_path: Path, wav_path: Path, settings: Settings) -> None:
    subprocess.run(
        [
            settings.fluidsynth_cmd,
            "-ni",
            "-F", str(wav_path),
            "-r", "44100",
            settings.soundfont_path,
            str(midi_path),
        ],
        check=True,
        capture_output=True,
    )


def _wav_to_mp3(wav_path: Path, mp3_path: Path, settings: Settings) -> None:
    subprocess.run(
        [
            settings.ffmpeg_cmd,
            "-y",
            "-i", str(wav_path),
            "-codec:a", "libmp3lame",
            "-qscale:a", "2",
            str(mp3_path),
        ],
        check=True,
        capture_output=True,
    )


def synthesize(
    midi_paths: dict[VoicePart, Path], out_dir: Path, settings: Settings
) -> dict[VoicePart, Path]:
    """Render every voice MIDI to an MP3. Returns voice -> mp3 path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results: dict[VoicePart, Path] = {}
    if not synthesis_available(settings):
        return results

    for voice, midi_path in midi_paths.items():
        wav_path = out_dir / f"{voice.value}.wav"
        mp3_path = out_dir / f"{voice.value}.mp3"
        try:
            _midi_to_wav(midi_path, wav_path, settings)
            _wav_to_mp3(wav_path, mp3_path, settings)
        except subprocess.CalledProcessError:
            continue
        finally:
            wav_path.unlink(missing_ok=True)
        results[voice] = mp3_path
    return results
