"""Tonic Sol-fa <-> staff notation conversion.

Two directions are supported:

* ``score_to_solfa`` / ``part_to_solfa`` - turn OMR/MusicXML notation into
  readable Curwen tonic sol-fa text (for display and download).
* ``solfa_to_musicxml`` - parse an uploaded tonic sol-fa piece into MusicXML so
  the existing extraction + synthesis pipeline can render a stave and audio.

Notation conventions (Curwen movable-doh):

* Syllables ``d r m f s l t`` (doh ray me fah soh lah te). Raised chromatics use
  the ``-e`` series ``de re fe se le`` which, together with the naturals, cover
  all twelve degrees uniquely so the mapping round-trips cleanly. Full English
  names (``doh``..``te``) and movable-doh solfege (``do re mi fa sol la ti`` and
  ``di ri fi si li``) are accepted on input.
* Octave marks: ``'`` (apostrophe) raises a doh-octave, ``,`` (comma) lowers it,
  relative to the reference doh placed in octave 4.
* Rhythm grid: ``|`` bars a measure, ``:`` separates beats, ``.`` splits a beat
  into equal subdivisions, ``-`` holds the previous note, and an empty slot or
  ``r`` is a rest.

Example::

    key: C
    time: 4/4
    tempo: 96

    soprano: d : r : m : f | m : r : d : - |
    alto:    s, : s, : d : d | d : t, : d : - |
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from ..models import VoicePart

SOLFA_SUFFIXES = {".sol", ".solfa", ".txt"}

# Canonical Curwen syllables emitted by the generator, indexed by the number of
# semitones above the tonic. Naturals + the raised ``-e`` series uniquely cover
# all twelve chromatic degrees.
_DEGREE_TO_SOLFA = {
    0: "d", 1: "de", 2: "r", 3: "re", 4: "m", 5: "f",
    6: "fe", 7: "s", 8: "se", 9: "l", 10: "le", 11: "t",
}

# Accepted input syllables -> semitone degree. Forgiving: Curwen, full English
# names and movable-doh solfege all resolve here.
_SOLFA_TO_DEGREE = {
    "d": 0, "doh": 0, "do": 0,
    "de": 1, "di": 1,
    "r": 2, "ray": 2, "ra": 2,
    "re": 3, "ri": 3,
    "m": 4, "me": 4, "mi": 4,
    "f": 5, "fah": 5, "fa": 5,
    "fe": 6, "fi": 6,
    "s": 7, "soh": 7, "so": 7, "sol": 7,
    "se": 8, "si": 8,
    "l": 9, "lah": 9, "la": 9,
    "le": 10, "li": 10,
    "t": 11, "te": 11, "ti": 11,
}

_REF_OCTAVE = 4  # reference doh sits here; commas/apostrophes shift from it.
_TOKEN_RE = re.compile(r"^([A-Za-z]+)([',]*)$")


def is_solfa_filename(filename: str) -> bool:
    return Path(filename).suffix.lower() in SOLFA_SUFFIXES


# ---------------------------------------------------------------------------
# Staff notation -> tonic sol-fa
# ---------------------------------------------------------------------------
def _solfa_for_pitch(midi: int, tonic_pc: int, ref_doh_midi: int) -> str:
    degree = (midi - tonic_pc) % 12
    syllable = _DEGREE_TO_SOLFA[degree]
    # Octave band relative to the reference doh (doh..te spans one band).
    offset = (midi - degree - ref_doh_midi) // 12
    if offset > 0:
        syllable += "'" * offset
    elif offset < 0:
        syllable += "," * (-offset)
    return syllable


def part_to_solfa(part, tonic_pc: int, ref_doh_midi: int) -> str:
    """Render a single music21 part as a tonic sol-fa rhythm grid."""
    from music21 import meter

    measures = list(part.getElementsByClass("Measure"))
    if not measures:
        part = part.makeMeasures()
        measures = list(part.getElementsByClass("Measure"))

    ts = part.recurse().getElementsByClass(meter.TimeSignature)
    if ts:
        beats = ts[0].numerator
        beat_len = 4.0 / ts[0].denominator
    else:
        beats, beat_len = 4, 1.0

    lines: list[str] = []
    for measure in measures:
        slots: list[str] = ["" for _ in range(beats)]
        for el in measure.notesAndRests:
            off = float(el.offset)
            idx = int(off // beat_len)
            if idx < 0 or idx >= beats:
                continue
            if el.isRest:
                token = "r"
            else:
                pitch = el.pitches[-1] if el.isChord else el.pitch
                token = _solfa_for_pitch(pitch.midi, tonic_pc, ref_doh_midi)
            slots[idx] = f"{slots[idx]}.{token}" if slots[idx] else token
            # Mark whole beats covered by a long note as holds.
            span = max(1, int(round(float(el.quarterLength) / beat_len)))
            for j in range(idx + 1, min(idx + span, beats)):
                if not slots[j]:
                    slots[j] = "-"
        cells = [s if s else "-" for s in slots]
        lines.append(" : ".join(cells))
    return " | ".join(lines) + (" |" if lines else "")


def score_to_solfa(musicxml: str) -> tuple[dict[VoicePart, str], str]:
    """Classify the score's parts and render each as tonic sol-fa text.

    Returns ``(by_voice, key_name)``. Voice classification reuses the same
    name/order heuristics as part extraction so the sol-fa lines line up with
    the audio stems.
    """
    from music21 import converter

    from .parts import _expand_voices, _VOICE_KEYWORDS, _VOICE_TOP_TO_BOTTOM

    score = converter.parseData(musicxml, format="musicxml")
    parts = _expand_voices(list(score.parts) if hasattr(score, "parts") else [])
    if not parts:
        return {}, "C"

    try:
        analysed = score.analyze("key")
        tonic_pc = analysed.tonic.pitchClass
        key_name = analysed.tonic.name
        # Anchor the reference doh to octave 4 for consistent octave marks.
        ref_doh_midi = tonic_pc + 12 * (_REF_OCTAVE + 1)
    except Exception:
        tonic_pc = 0
        key_name = "C"
        ref_doh_midi = 12 * (_REF_OCTAVE + 1)

    # Classify each part by printed name, then fill the rest top-to-bottom.
    def classify(name: str):
        lowered = (name or "").lower()
        for voice, keywords in _VOICE_KEYWORDS.items():
            if any(kw in lowered for kw in keywords):
                return voice
        return None

    assignments: dict[int, VoicePart] = {}
    unassigned: list[int] = []
    for idx, part in enumerate(parts):
        voice = classify(str(part.partName or part.id or ""))
        if voice is not None and voice not in assignments.values():
            assignments[idx] = voice
        else:
            unassigned.append(idx)
    remaining = [v for v in _VOICE_TOP_TO_BOTTOM if v not in assignments.values()]
    for i, part_idx in enumerate(sorted(unassigned)):
        if i < len(remaining):
            assignments[part_idx] = remaining[i]

    out: dict[VoicePart, str] = {}
    for idx, part in enumerate(parts):
        voice = assignments.get(idx)
        if voice is None:
            continue
        out[voice] = part_to_solfa(part, tonic_pc, ref_doh_midi)
    return out, key_name


def combined_solfa_text(
    by_voice: dict[VoicePart, str], key_name: str = "C"
) -> str:
    """A single labelled, downloadable sol-fa document for the whole piece."""
    order = [VoicePart.SOPRANO, VoicePart.ALTO, VoicePart.TENOR, VoicePart.BASS]
    lines = [f"key: {key_name}", ""]
    for voice in order:
        if voice in by_voice:
            lines.append(f"{voice.value}: {by_voice[voice]}")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Tonic sol-fa -> staff notation
# ---------------------------------------------------------------------------
@dataclass
class _ParsedSolfa:
    key_name: str = "C"
    mode: str = "major"
    time_sig: str = "4/4"
    tempo: int = 96
    voices: dict[str, str] = field(default_factory=dict)


def _parse_header_and_voices(text: str) -> _ParsedSolfa:
    parsed = _ParsedSolfa()
    current: str | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue

        header = re.match(r"^(key|doh|time|tempo)\s*[:=]\s*(.+)$", line, re.I)
        voice = re.match(r"^(soprano|alto|tenor|bass)\s*:\s*(.*)$", line, re.I)

        if voice:
            current = voice.group(1).lower()
            parsed.voices[current] = voice.group(2).strip()
            continue
        if header:
            field_name = header.group(1).lower()
            value = header.group(2).strip()
            if field_name in ("key", "doh"):
                m = re.match(r"^([A-Ga-g][#b]?)\s*(major|minor|maj|min)?", value)
                if m:
                    parsed.key_name = m.group(1).capitalize()
                    if m.group(2) and m.group(2).lower().startswith("min"):
                        parsed.mode = "minor"
            elif field_name == "time":
                if re.match(r"^\d+\s*/\s*\d+$", value):
                    parsed.time_sig = value.replace(" ", "")
            elif field_name == "tempo":
                try:
                    parsed.tempo = int(re.findall(r"\d+", value)[0])
                except (IndexError, ValueError):
                    pass
            continue

        # Continuation of the current voice block.
        if current is not None:
            parsed.voices[current] = f"{parsed.voices[current]} {line}".strip()

    # No explicit voice headers: treat the whole body as a single soprano line.
    if not parsed.voices:
        body = " ".join(
            l.strip()
            for l in text.splitlines()
            if l.strip()
            and not re.match(r"^(key|doh|time|tempo)\s*[:=]", l.strip(), re.I)
        )
        if body:
            parsed.voices["soprano"] = body
    return parsed


def _syllable_to_midi(token: str, tonic_pc: int, ref_doh_midi: int) -> int | None:
    match = _TOKEN_RE.match(token)
    if not match:
        return None
    name, marks = match.group(1).lower(), match.group(2)
    if name not in _SOLFA_TO_DEGREE:
        return None
    degree = _SOLFA_TO_DEGREE[name]
    octave_shift = marks.count("'") - marks.count(",")
    return ref_doh_midi + degree + 12 * octave_shift


def _build_part(content: str, voice: str, parsed: _ParsedSolfa, ref_doh_midi: int):
    from music21 import clef, instrument, key as m21key, meter, note, stream, tempo

    den = int(parsed.time_sig.split("/")[1])
    beat_len = 4.0 / den
    tonic_pc = m21key.Key(parsed.key_name).tonic.pitchClass

    part = stream.Part()
    part.id = voice.capitalize()
    part.partName = voice.capitalize()
    part.insert(0, instrument.Vocalist())
    clefs = {
        "soprano": clef.TrebleClef, "alto": clef.TrebleClef,
        "tenor": clef.Treble8vbClef, "bass": clef.BassClef,
    }
    part.append(clefs.get(voice, clef.TrebleClef)())
    part.append(m21key.Key(parsed.key_name, parsed.mode))
    part.append(meter.TimeSignature(parsed.time_sig))
    if voice == "soprano":
        part.insert(0, tempo.MetronomeMark(number=parsed.tempo))

    last_note: note.Note | None = None
    for measure in content.split("|"):
        measure = measure.strip()
        if not measure:
            continue
        for beat in measure.split(":"):
            beat = beat.strip()
            subs = [s for s in beat.split(".")] if beat else [""]
            slot_len = beat_len / max(1, len(subs))
            for sub in subs:
                sub = sub.strip()
                if sub in ("", "r", "R"):
                    part.append(note.Rest(quarterLength=slot_len))
                    last_note = None
                elif sub == "-":
                    if last_note is not None:
                        last_note.quarterLength += slot_len
                    else:
                        part.append(note.Rest(quarterLength=slot_len))
                else:
                    midi = _syllable_to_midi(sub, tonic_pc, ref_doh_midi)
                    if midi is None:
                        part.append(note.Rest(quarterLength=slot_len))
                        last_note = None
                    else:
                        n = note.Note()
                        n.pitch.midi = midi
                        n.quarterLength = slot_len
                        part.append(n)
                        last_note = n
    return part


def solfa_to_score(text: str):
    """Parse tonic sol-fa text into a music21 :class:`~music21.stream.Score`."""
    from music21 import key as m21key, stream

    parsed = _parse_header_and_voices(text)
    if not parsed.voices:
        raise ValueError("No tonic sol-fa content found.")

    tonic_pc = m21key.Key(parsed.key_name).tonic.pitchClass
    ref_doh_midi = tonic_pc + 12 * (_REF_OCTAVE + 1)

    order = ["soprano", "alto", "tenor", "bass"]
    score = stream.Score()
    for voice in order:
        if voice not in parsed.voices:
            continue
        part = _build_part(parsed.voices[voice], voice, parsed, ref_doh_midi)
        if part.recurse().notes:
            score.insert(0, part)
    if not score.parts:
        raise ValueError("Tonic sol-fa parsed to an empty score.")
    return score


def solfa_to_musicxml(text: str) -> str:
    """Convert tonic sol-fa text to MusicXML for the rendering pipeline."""
    from music21.musicxml.m21ToXml import GeneralObjectExporter

    score = solfa_to_score(text)
    return GeneralObjectExporter(score).parse().decode("utf-8")
