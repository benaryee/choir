"""Stage 3 - voice-part extraction with music21.

Parses the OMR MusicXML, classifies each part as Soprano/Alto/Tenor/Bass and
writes per-voice MusicXML + MIDI plus a merged full-SATB MIDI.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from ..models import DetectedPart, VoicePart

# Keyword hints used to map a part's printed name onto an SATB voice.
_VOICE_KEYWORDS: dict[VoicePart, tuple[str, ...]] = {
    VoicePart.SOPRANO: ("soprano", "sop", "s.", "descant", "treble 1"),
    VoicePart.ALTO: ("alto", "alt", "a.", "contralto", "mezzo"),
    VoicePart.TENOR: ("tenor", "ten", "t.", "tenore"),
    VoicePart.BASS: ("bass", "bari", "baritone", "b.", "basso"),
}

# Standard choral score layout, top staff to bottom. Used as the fallback when
# parts carry no usable name (Audiveris often exports every part as "Voice").
_VOICE_TOP_TO_BOTTOM = [VoicePart.SOPRANO, VoicePart.ALTO, VoicePart.TENOR, VoicePart.BASS]


@dataclass
class ExtractedParts:
    musicxml_paths: dict[VoicePart, Path] = field(default_factory=dict)
    midi_paths: dict[VoicePart, Path] = field(default_factory=dict)
    detected: list[DetectedPart] = field(default_factory=list)


def _classify_by_name(name: str) -> VoicePart | None:
    lowered = (name or "").lower()
    for voice, keywords in _VOICE_KEYWORDS.items():
        if any(kw in lowered for kw in keywords):
            return voice
    return None


def _confidence_for(name_match: bool) -> float:
    return 0.9 if name_match else 0.5


def _expand_voices(parts: list) -> list:
    """Flatten closed-score staves into one stream per voice.

    Hymn/piano-style choral scores notate multiple voices on a single staff
    (e.g. Soprano+Alto on the treble staff). music21 cannot write such a
    multi-voice part to MusicXML (it raises ``KeyError`` in ``makeTies``), and
    treating the staff as one voice would also drop half the singers. We split
    each multi-voice staff with ``voicesToParts`` (which separates the voices
    and back-fills rests, so each result writes cleanly) and discard the
    fragmentary phantom voices OMR engines often emit. Single-voice staves are
    returned unchanged.
    """
    expanded: list = []
    for part in parts:
        measures = part.getElementsByClass("Measure")
        if not any(len(m.voices) > 1 for m in measures):
            expanded.append(part)
            continue

        split = part.voicesToParts()
        subparts = list(split.parts) if hasattr(split, "parts") else [split]
        counts = [len(sp.recurse().notes) for sp in subparts]
        peak = max(counts) if counts else 0
        for subpart, count in zip(subparts, counts):
            # Drop empty/fragmentary voices (OMR noise) relative to the staff's
            # strongest voice; keep the genuine simultaneous lines.
            if count == 0 or count < 0.25 * peak:
                continue
            subpart.partName = part.partName
            expanded.append(subpart)
    return expanded


def extract_parts(musicxml: str, out_dir: Path, basename: str = "part") -> ExtractedParts:
    """Split ``musicxml`` into per-voice streams and render MIDI for each."""
    from music21 import converter, midi, stream

    out_dir.mkdir(parents=True, exist_ok=True)
    score = converter.parseData(musicxml, format="musicxml")
    parts = _expand_voices(list(score.parts) if hasattr(score, "parts") else [])

    result = ExtractedParts()
    if not parts:
        return result

    # First pass: name-based classification.
    assignments: dict[int, VoicePart] = {}
    unassigned: list[int] = []
    for idx, part in enumerate(parts):
        name = part.partName or part.id or ""
        voice = _classify_by_name(str(name))
        if voice is not None and voice not in assignments.values():
            assignments[idx] = voice
        else:
            unassigned.append(idx)

    # Second pass: assign leftovers to the remaining voices following the score's
    # top-to-bottom staff order (the standard SATB layout). This is far more
    # robust than averaging pitches, which misfires on octave-displaced parts
    # such as a tenor line notated an octave up on a treble-8 clef.
    remaining = [v for v in _VOICE_TOP_TO_BOTTOM if v not in assignments.values()]
    for i, part_idx in enumerate(sorted(unassigned)):
        if i < len(remaining):
            assignments[part_idx] = remaining[i]

    full_score = stream.Score()

    for idx, part in enumerate(parts):
        voice = assignments.get(idx)
        printed = str(part.partName or part.id or f"Part {idx + 1}")
        name_match = _classify_by_name(printed) is not None
        result.detected.append(
            DetectedPart(
                id=f"p{idx}",
                label=printed,
                suggested_voice=voice,
                confidence=_confidence_for(name_match),
            )
        )
        if voice is None:
            continue

        full_score.insert(0, part)

        xml_path = out_dir / f"{basename}_{voice.value}.musicxml"
        part.write("musicxml", fp=str(xml_path))
        result.musicxml_paths[voice] = xml_path

        midi_path = out_dir / f"{basename}_{voice.value}.mid"
        mf = midi.translate.streamToMidiFile(part)
        mf.open(str(midi_path), "wb")
        mf.write()
        mf.close()
        result.midi_paths[voice] = midi_path

    # Merged full-choir MIDI.
    if len(full_score.parts) > 0:
        full_midi = out_dir / f"{basename}_full.mid"
        mf = midi.translate.streamToMidiFile(full_score)
        mf.open(str(full_midi), "wb")
        mf.write()
        mf.close()
        result.midi_paths[VoicePart.FULL] = full_midi

    return result
