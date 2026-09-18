"""Pitches, intervals, and the chord-symbol parser everything else reads.

Pitch is an integer MIDI number throughout; pitch *class* is that number mod
12. Keeping both as plain ints rather than objects is deliberate — the arranger
evaluates hundreds of thousands of candidate voicings, and every comparison in
the inner loop is an integer subtraction.

The one place that cannot be integers is spelling. F-sharp and G-flat are the
same key on a piano and different notes on a page: the first is the leading
tone of G major, the second is the fourth degree of D-flat. The engine works in
pitch classes and only re-spells at the edges, where notation is produced.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Semitones above C for each letter name.
LETTER_SEMITONES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}

SHARP_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
FLAT_NAMES = ["C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B"]

#: MIDI 60 is middle C, which every other number here is relative to.
MIDDLE_C = 60

#: An 88-key piano runs A0 to C8.
LOWEST_KEY = 21
HIGHEST_KEY = 108


class ChordError(ValueError):
    """A chord symbol that cannot be read."""


def pitch_class(pitch: int) -> int:
    return pitch % 12


def note_name(pitch: int, flats: bool = False) -> str:
    """MIDI number to a name with an octave, e.g. 60 -> 'C4'."""
    names = FLAT_NAMES if flats else SHARP_NAMES
    return f"{names[pitch % 12]}{pitch // 12 - 1}"


def parse_note(text: str) -> int:
    """'C4', 'Bb3', 'F#5' to a MIDI number."""
    match = re.fullmatch(r"([A-Ga-g])([#b]*)(-?\d+)", text.strip())
    if not match:
        raise ChordError(f"not a note: {text!r}")
    letter, accidentals, octave = match.groups()
    value = LETTER_SEMITONES[letter.upper()]
    value += accidentals.count("#") - accidentals.count("b")
    return value + (int(octave) + 1) * 12


#: Chord qualities as semitone offsets from the root.
#:
#: Ordered longest-suffix-first when matched, so that "maj7" is not read as
#: "ma" + garbage and "m7b5" is not read as "m7" with a stray "b5".
QUALITIES: dict[str, tuple[int, ...]] = {
    # triads
    "": (0, 4, 7),
    "maj": (0, 4, 7),
    "M": (0, 4, 7),
    "m": (0, 3, 7),
    "min": (0, 3, 7),
    "-": (0, 3, 7),
    "dim": (0, 3, 6),
    "o": (0, 3, 6),
    "aug": (0, 4, 8),
    "+": (0, 4, 8),
    "sus2": (0, 2, 7),
    "sus4": (0, 5, 7),
    "sus": (0, 5, 7),
    # sevenths
    "7": (0, 4, 7, 10),
    "maj7": (0, 4, 7, 11),
    "M7": (0, 4, 7, 11),
    "Δ": (0, 4, 7, 11),
    "Δ7": (0, 4, 7, 11),
    "m7": (0, 3, 7, 10),
    "min7": (0, 3, 7, 10),
    "-7": (0, 3, 7, 10),
    "mmaj7": (0, 3, 7, 11),
    "mM7": (0, 3, 7, 11),
    "dim7": (0, 3, 6, 9),
    "o7": (0, 3, 6, 9),
    "m7b5": (0, 3, 6, 10),
    "ø": (0, 3, 6, 10),
    "ø7": (0, 3, 6, 10),
    "7sus4": (0, 5, 7, 10),
    "7sus": (0, 5, 7, 10),
    "6": (0, 4, 7, 9),
    "m6": (0, 3, 7, 9),
    "aug7": (0, 4, 8, 10),
    "7#5": (0, 4, 8, 10),
    "7b5": (0, 4, 6, 10),
    # extensions, voiced as the shell plus the extension
    "9": (0, 4, 7, 10, 14),
    "maj9": (0, 4, 7, 11, 14),
    "M9": (0, 4, 7, 11, 14),
    "m9": (0, 3, 7, 10, 14),
    "11": (0, 4, 7, 10, 14, 17),
    "m11": (0, 3, 7, 10, 14, 17),
    "13": (0, 4, 7, 10, 14, 21),
    "maj13": (0, 4, 7, 11, 14, 21),
    "m13": (0, 3, 7, 10, 14, 21),
    "7b9": (0, 4, 7, 10, 13),
    "7#9": (0, 4, 7, 10, 15),
    "7#11": (0, 4, 7, 10, 18),
    "7b13": (0, 4, 7, 10, 20),
    "add9": (0, 4, 7, 14),
    "madd9": (0, 3, 7, 14),
    "5": (0, 7),
}

#: Which chord tone each interval is, for naming and for deciding what may be
#: dropped. The third and seventh define the quality; the fifth rarely does.
DEGREE_OF_INTERVAL = {
    0: "root", 2: "9th", 3: "3rd", 4: "3rd", 5: "11th", 6: "5th", 7: "5th",
    8: "5th", 9: "6th", 10: "7th", 11: "7th", 13: "9th", 14: "9th", 15: "9th",
    17: "11th", 18: "11th", 20: "13th", 21: "13th",
}

_ROOT = re.compile(r"^([A-Ga-g])([#b]*)")


@dataclass(frozen=True)
class Chord:
    """A chord symbol, parsed.

    `intervals` are semitones above the root, unvoiced — the chord as an
    abstract set of tones, before anything decides which octave each lands in
    or whether a hand can reach them. That decision belongs to the arranger.
    """

    symbol: str
    root: int
    quality: str
    intervals: tuple[int, ...]
    bass: int | None = None

    @property
    def pitch_classes(self) -> tuple[int, ...]:
        return tuple(sorted({(self.root + i) % 12 for i in self.intervals}))

    @property
    def is_slash(self) -> bool:
        """Is a bass note specified that is not the root?"""
        return self.bass is not None and self.bass % 12 != self.root % 12

    @property
    def essential(self) -> tuple[int, ...]:
        """Tones that may not be dropped: root, third (or sus), seventh.

        The fifth is droppable because it is implied by the root and adds no
        information about quality — dropping it is the standard way to free a
        finger. The third is what makes a chord major or minor, so a voicing
        without it is a different chord.
        """
        keep = [0]
        for interval in self.intervals:
            degree = DEGREE_OF_INTERVAL.get(interval % 24, "")
            if degree in {"3rd", "7th"} or (degree == "11th" and "sus" in self.quality):
                keep.append(interval)
        return tuple(sorted(set(keep)))

    def __str__(self) -> str:
        return self.symbol


def parse_chord(symbol: str) -> Chord:
    """Read a chord symbol: 'C', 'Am7', 'F#m7b5', 'G7/B', 'Bbmaj9'."""
    text = symbol.strip()
    if not text:
        raise ChordError("empty chord symbol")

    bass = None
    if "/" in text:
        text, _, bass_text = text.partition("/")
        bass = parse_note(bass_text + "2") % 12 if not bass_text[-1:].isdigit() \
            else parse_note(bass_text) % 12

    match = _ROOT.match(text)
    if not match:
        raise ChordError(f"no root note in {symbol!r}")
    letter, accidentals = match.groups()
    root = (
        LETTER_SEMITONES[letter.upper()]
        + accidentals.count("#")
        - accidentals.count("b")
    ) % 12

    suffix = text[match.end():]
    # Longest match first, so "maj7" wins over "maj" and "m7b5" over "m7".
    for quality in sorted(QUALITIES, key=len, reverse=True):
        if suffix == quality:
            return Chord(symbol.strip(), root, quality, QUALITIES[quality], bass)
    raise ChordError(f"unknown chord quality {suffix!r} in {symbol!r}")


def parse_progression(text: str) -> list[Chord]:
    """A whitespace- or bar-separated chart: 'C Am | F G7'."""
    tokens = [t for t in re.split(r"[\s|,]+", text.strip()) if t]
    if not tokens:
        raise ChordError("no chords found")
    return [parse_chord(t) for t in tokens]
