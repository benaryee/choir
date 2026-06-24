"""Generates a valid SATB MusicXML sample.

Used as the final OMR fallback so the upload -> OMR -> MusicXML -> parts flow
runs end to end in local dev without Audiveris or an OpenAI key configured.
"""
from __future__ import annotations

from functools import lru_cache


@lru_cache
def sample_satb_musicxml() -> str:
    """Build a short 4-bar SATB chorale and return it as MusicXML text."""
    from music21 import clef, instrument, key, meter, note, stream, tempo

    # Simple diatonic lines per voice (MIDI-ish note names).
    lines = {
        "Soprano": ["C5", "D5", "E5", "F5", "E5", "D5", "C5", "C5"],
        "Alto": ["E4", "F4", "G4", "A4", "G4", "F4", "E4", "E4"],
        "Tenor": ["G3", "A3", "B3", "C4", "B3", "A3", "G3", "G3"],
        "Bass": ["C3", "B2", "A2", "F2", "G2", "G2", "C3", "C3"],
    }
    clefs = {
        "Soprano": clef.TrebleClef(),
        "Alto": clef.TrebleClef(),
        "Tenor": clef.Treble8vbClef(),
        "Bass": clef.BassClef(),
    }

    score = stream.Score()
    score.insert(0, tempo.MetronomeMark(number=92))
    for name, pitches in lines.items():
        part = stream.Part()
        part.id = name
        part.partName = name
        part.insert(0, instrument.Vocalist())
        part.append(clefs[name])
        part.append(key.KeySignature(0))
        part.append(meter.TimeSignature("4/4"))
        for p in pitches:
            part.append(note.Note(p, quarterLength=1.0))
        score.insert(0, part)

    from music21.musicxml.m21ToXml import GeneralObjectExporter

    return GeneralObjectExporter(score).parse().decode("utf-8")
