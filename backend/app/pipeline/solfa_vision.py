"""Claude transcription of tonic sol-fa page images.

Audiveris and the GPT-4o prompt both expect staff notation, so a score printed
in tonic sol-fa (common for West African and British hymnal choirs) comes back
near-empty. This module asks Claude to read the page images, decide which
notation they use and, for sol-fa, rewrite every voice in the text grammar that
:mod:`.solfa` parses. The caller then renders it to MusicXML the same way as an
uploaded ``.solfa`` file.
"""
from __future__ import annotations

import base64
import json
import logging
import re
from pathlib import Path

from ..config import Settings

logger = logging.getLogger(__name__)

_VOICES = ("soprano", "alto", "tenor", "bass")

TRANSCRIBE_PROMPT = """\
These images are the pages of one choral score, in order. First decide which \
notation it is written in:
- "tonic_solfa": Curwen tonic sol-fa (syllables d r m f s l t with : and | \
rhythm marks, no five-line staves)
- "staff": ordinary staff notation on five-line staves
- "other": anything else, or not music

If it is not tonic sol-fa, return that notation with empty strings for the \
other fields. Otherwise transcribe every voice into the plain-text grammar \
below. A program parses your output, so follow the grammar exactly.

Grammar (one string per voice):
- "|" ends every measure; ":" separates beats within a measure. Every measure \
of every voice must contain exactly the number of beats in the time signature, \
including the first (pickup) measure; pad a pickup with rest beats in front.
- "." splits a beat into EQUAL parts. Write the printed uneven divisions as \
equal quarters: ".," (3/4 + 1/4) such as "d .,r" becomes "d.-.-.r"; a beat \
that starts ".,s" (rest then a quarter-beat note) becomes "R.R.R.s"; "-.,s" \
becomes "-.-.-.s".
- Syllables: d r m f s l t; raised de re fe se le; flattened ta (and ma). Use \
lowercase only.
- Octave marks go right after the syllable: "," for each octave down \
(subscript 1 in print, e.g. s₁ -> "s,", s₂ -> "s,,") and "'" for each octave \
up (superscript 1 in print, e.g. d¹ -> "d'"). Copy the marks exactly as printed; \
do not transpose the tenor or bass lines yourself.
- "-" continues (holds) the previous note for that slot. "R" is a rest; an \
empty beat or empty slot in print is a rest, so write "R" for it.
- Ignore lyrics, dynamics, bar numbers and slurs. Ignore the underlines that \
some scores draw under groups of notes.

Voices: in a four-part system the rows are, top to bottom, soprano, alto, \
tenor, bass; a row of lyrics may sit between alto and tenor. If the score has \
fewer parts, leave the missing voices empty.

Repeats: write the music out in performance order. Expand D.C. / D.S. / \
repeat signs so each voice is one continuous line, stopping at Fine or at the \
marked ending. If you can't tell where a D.C. or D.S. should stop, don't \
expand it; transcribe the pages once in order.

key: the printed doh key, e.g. "KEY: G" or "Doh is G" -> "G" (use "Bb", "F#" \
etc. for accidentals, and add " minor" only if the score says so).
time: the time signature as "beats/4"; sol-fa scores often print only the beat \
count, so "Time: 2" -> "2/4".

Before answering, check that all voices have the same number of measures and \
every measure has the right number of beats. Fix any mismatch by re-reading \
that measure in the image.
"""

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "notation": {"type": "string", "enum": ["tonic_solfa", "staff", "other"]},
        "key": {"type": "string"},
        "time": {"type": "string"},
        **{voice: {"type": "string"} for voice in _VOICES},
    },
    "required": ["notation", "key", "time", *_VOICES],
    "additionalProperties": False,
}


_MAX_IMAGE_BYTES = 4_500_000  # the API rejects images over 5 MB
_DOWNSCALE_LONG_EDGE = 2400


def _image_block(path: Path) -> dict:
    data = path.read_bytes()
    media_type = "image/jpeg" if path.suffix.lower() in (".jpg", ".jpeg") else "image/png"
    if len(data) > _MAX_IMAGE_BYTES:
        # Noisy scans at 300 dpi can exceed the limit; a grayscale page at
        # ~200 dpi keeps sol-fa subscripts legible at a fraction of the size.
        import cv2

        gray = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
        scale = _DOWNSCALE_LONG_EDGE / max(gray.shape)
        if scale < 1:
            gray = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        data = cv2.imencode(".png", gray)[1].tobytes()
        media_type = "image/png"
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": media_type,
            "data": base64.standard_b64encode(data).decode("ascii"),
        },
    }


def _fit_measures(voice_text: str, beats: int) -> tuple[str, list[int]]:
    """Pad/trim each measure to ``beats`` beats so a misread can't desync voices.

    Returns the fixed text and the 1-based numbers of the measures it changed.
    """
    measures = [m.strip() for m in voice_text.split("|") if m.strip()]
    fixed: list[str] = []
    changed: list[int] = []
    for number, measure in enumerate(measures, start=1):
        cells = [c.strip() for c in measure.split(":")]
        if len(cells) != beats:
            changed.append(number)
            cells = (cells + ["-"] * beats)[:beats]
        fixed.append(" : ".join(cells))
    return " | ".join(fixed) + " |", changed


def _normalise_grid(data: dict) -> None:
    """Keep every voice on the time signature's beat grid, logging any repairs."""
    time = data.get("time", "")
    if not re.match(r"^\d+/\d+$", time):
        return
    beats = int(time.split("/")[0])
    counts: dict[str, int] = {}
    for voice in _VOICES:
        if not data.get(voice, "").strip():
            continue
        data[voice], changed = _fit_measures(data[voice], beats)
        counts[voice] = data[voice].count("|")
        if changed:
            logger.warning(
                "Sol-fa transcription %s: padded/trimmed measures %s to %d beats",
                voice, changed[:10], beats,
            )
    if len(set(counts.values())) > 1:
        logger.warning("Sol-fa transcription measure counts differ: %s", counts)


def transcribe_solfa_pages(image_paths: list[Path], settings: Settings) -> str | None:
    """Return the pages as sol-fa text for :func:`.solfa.solfa_to_musicxml`.

    Returns ``None`` when Claude isn't configured, the call fails, or the pages
    aren't tonic sol-fa - the caller then continues down the OMR cascade.
    """
    if not settings.anthropic_api_key or not image_paths:
        return None
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    content: list[dict] = [_image_block(p) for p in image_paths]
    content.append({"type": "text", "text": TRANSCRIBE_PROMPT})

    try:
        # Streaming: a full score can be a long response, which would risk an
        # HTTP timeout as a single blocking request.
        with client.beta.messages.stream(
            model=settings.anthropic_vision_model,
            max_tokens=64000,
            thinking={"type": "adaptive"},
            output_config={
                "effort": "high",
                "format": {"type": "json_schema", "schema": _OUTPUT_SCHEMA},
            },
            # Re-run on Anthropic's recommended model if a safety classifier
            # declines the request, instead of failing the job.
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": content}],
        ) as stream:
            message = stream.get_final_message()
    except anthropic.APIError as exc:
        logger.warning("Claude sol-fa transcription failed: %s", exc)
        return None

    if message.stop_reason != "end_turn":
        logger.warning(
            "Claude sol-fa transcription stopped early (%s, request %s)",
            message.stop_reason, message._request_id,
        )
        return None

    text = next((b.text for b in message.content if b.type == "text"), "")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        logger.warning("Claude sol-fa transcription returned invalid JSON")
        return None

    if data.get("notation") != "tonic_solfa":
        logger.info("Claude reports %s notation; not a sol-fa score", data.get("notation"))
        return None
    if not any(data.get(v, "").strip() for v in _VOICES):
        return None

    _normalise_grid(data)

    lines = [f"key: {data.get('key') or 'C'}"]
    if data.get("time"):
        lines.append(f"time: {data['time']}")
    lines.append("")
    for voice in _VOICES:
        if data.get(voice, "").strip():
            lines.append(f"{voice}: {data[voice].strip()}")
    return "\n".join(lines) + "\n"
