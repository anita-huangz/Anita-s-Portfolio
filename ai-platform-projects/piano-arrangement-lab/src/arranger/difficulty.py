"""What "beginner" actually means, as numbers the solver can enforce.

Difficulty in piano writing is not a vague adjective. It is a small set of
physical and cognitive limits — how far the hand stretches, how many notes it
tracks at once, whether the left hand has to move while the right hand plays —
and each of them is a constraint the search can respect exactly.

Stating them as data rather than as prose is what makes the claim testable:
`test_difficulty.py` asserts that no beginner arrangement ever exceeds the
beginner hand span, over every chord in the test corpus. A generator that
merely *tried* to be easy could not be checked that way.
"""

from __future__ import annotations

from dataclasses import dataclass

from .theory import MIDDLE_C


@dataclass(frozen=True)
class Level:
    """A difficulty tier."""

    name: str
    #: Largest interval either hand must span, in semitones. 12 is an octave.
    #: A child or a beginning adult reliably reaches a sixth to an octave;
    #: tenths are a professional stretch and are simply unavailable below it.
    max_span: int
    #: Most notes struck at once by the right hand, and by the left.
    max_right_notes: int
    max_left_notes: int
    #: May the *lowest sounding note* be something other than the chord root?
    #: This governs the bass, not how the right hand stacks the chord: with the
    #: root in the left hand the chord is in root position however the right
    #: hand arranges it, and forbidding right-hand inversions as well would
    #: leave ordinary chords like Am7 unplayable inside a beginner's register.
    allow_inversions: bool
    #: May tones above the seventh (9ths, 11ths, 13ths) be voiced?
    allow_extensions: bool
    #: Register the right hand is kept inside, as MIDI numbers.
    right_low: int
    right_high: int
    #: Register for the left hand.
    left_low: int
    left_high: int
    #: Penalty weight on moving a hand between chords. A beginner benefits
    #: much more from a still hand than an advanced player does, so the same
    #: motion costs more here.
    motion_weight: float
    #: How strongly voice-leading rule violations are punished relative to
    #: motion. Advanced writing tolerates a parallel fifth in a jazz voicing;
    #: a beginner chorale should not have one.
    rule_weight: float
    description: str


BEGINNER = Level(
    name="beginner",
    max_span=12,
    max_right_notes=3,
    max_left_notes=1,
    allow_inversions=False,
    allow_extensions=False,
    right_low=MIDDLE_C,
    right_high=MIDDLE_C + 19,
    left_low=MIDDLE_C - 24,
    left_high=MIDDLE_C - 5,
    motion_weight=2.0,
    rule_weight=1.0,
    description=(
        "Root-position chords only, a single bass note in the left hand, at most "
        "three notes in the right, nothing wider than an octave, no extensions "
        "and nothing outside the two octaves above middle C."
    ),
)

INTERMEDIATE = Level(
    name="intermediate",
    max_span=12,
    max_right_notes=4,
    max_left_notes=2,
    allow_inversions=True,
    allow_extensions=False,
    right_low=MIDDLE_C - 4,
    right_high=MIDDLE_C + 21,
    left_low=MIDDLE_C - 28,
    left_high=MIDDLE_C - 2,
    motion_weight=1.0,
    rule_weight=1.0,
    description=(
        "Sevenths and inversions are available, the left hand may play root and "
        "fifth together, and the solver is free to invert chords to keep the "
        "right hand still."
    ),
)

ADVANCED = Level(
    name="advanced",
    max_span=14,
    max_right_notes=5,
    max_left_notes=3,
    allow_inversions=True,
    allow_extensions=True,
    right_low=MIDDLE_C - 7,
    right_high=MIDDLE_C + 26,
    left_low=MIDDLE_C - 31,
    left_high=MIDDLE_C + 2,
    motion_weight=0.5,
    rule_weight=0.6,
    description=(
        "Extensions up to the 13th, tenths in the left hand, and a wider "
        "register. Motion is cheap, so the solver will move a hand to reach a "
        "richer voicing."
    ),
)

LEVELS: dict[str, Level] = {
    level.name: level for level in (BEGINNER, INTERMEDIATE, ADVANCED)
}
