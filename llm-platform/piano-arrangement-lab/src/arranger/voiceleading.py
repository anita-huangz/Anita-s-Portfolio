"""The rules that decide whether one voicing follows well from another.

These are the ordinary rules of part-writing, the ones a first-year harmony
course spends a term on. They exist because the ear tracks *lines*, not
chords: two voices moving in parallel fifths stop sounding like two voices and
collapse into one thickened line, and a voice that leaps a tenth and never
comes back sounds like a mistake because nothing can sing it.

Every rule returns a named violation rather than a silent number, so the
arranger can show its reasoning instead of asserting that its answer is good.
`explain()` turns a transition into the list a student would get back from a
teacher marking the page.
"""

from __future__ import annotations

from dataclasses import dataclass

from .difficulty import Level
from .voicing import Voicing

PERFECT_FIFTH = 7
OCTAVE = 12


@dataclass(frozen=True)
class Violation:
    """One broken rule, with enough detail to point at it on the page."""

    rule: str
    detail: str
    penalty: float


def _voices(voicing: Voicing) -> tuple[int, ...]:
    """Pitches low to high. Voice *i* is the i-th from the bottom."""
    return voicing.pitches


def _pairs_moving_same_way(
    previous: tuple[int, ...], current: tuple[int, ...]
) -> list[tuple[int, int, int, int]]:
    """Voice pairs that both moved, in the same direction, in both chords.

    Voices are matched by position from the bottom. That is an approximation
    when the two chords have different numbers of notes -- real part-writing
    tracks named voices -- but on a keyboard, where notes are not assigned to
    singers, position from the bottom is what the ear actually follows.
    """
    n = min(len(previous), len(current))
    out = []
    for i in range(n):
        for j in range(i + 1, n):
            before_i, before_j = previous[i], previous[j]
            after_i, after_j = current[i], current[j]
            step_i, step_j = after_i - before_i, after_j - before_j
            if step_i == 0 or step_j == 0:
                continue
            if (step_i > 0) != (step_j > 0):
                continue
            out.append((before_i, before_j, after_i, after_j))
    return out


def parallels(previous: Voicing, current: Voicing) -> list[Violation]:
    """Consecutive perfect fifths or octaves between the same pair of voices."""
    found = []
    for before_low, before_high, after_low, after_high in _pairs_moving_same_way(
        _voices(previous), _voices(current)
    ):
        before = (before_high - before_low) % OCTAVE
        after = (after_high - after_low) % OCTAVE
        if before != after:
            continue
        if before == PERFECT_FIFTH:
            found.append(Violation(
                "parallel fifths",
                f"{before_low}->{after_low} against {before_high}->{after_high}",
                4.0,
            ))
        elif before == 0 and (before_high - before_low) >= OCTAVE:
            found.append(Violation(
                "parallel octaves",
                f"{before_low}->{after_low} against {before_high}->{after_high}",
                4.0,
            ))
    return found


def leaps(previous: Voicing, current: Voicing) -> list[Violation]:
    """Voices that jump further than a sixth, and the melody further than an octave.

    An inner voice leaping is awkward to hear and awkward to play. The top
    voice is allowed more, because it is the melody and a melody may leap --
    but an octave is the point past which it stops sounding like one line.
    """
    found = []
    before, after = _voices(previous), _voices(current)
    n = min(len(before), len(after))
    for i in range(n):
        distance = abs(after[i] - before[i])
        top = i == n - 1
        limit = 12 if top else 9
        if distance > limit:
            found.append(Violation(
                "large leap",
                f"{'melody' if top else f'voice {i + 1}'} moves {distance} semitones",
                0.5 * (distance - limit),
            ))
    return found


def overlap(previous: Voicing, current: Voicing) -> list[Violation]:
    """A voice crossing below where the voice under it just was.

    The two lines swap places and the ear loses track of both.
    """
    found = []
    before, after = _voices(previous), _voices(current)
    n = min(len(before), len(after))
    for i in range(1, n):
        if after[i] < before[i - 1]:
            found.append(Violation(
                "voice overlap",
                f"voice {i + 1} falls to {after[i]}, below voice {i}'s {before[i - 1]}",
                1.5,
            ))
    return found


def motion(previous: Voicing, current: Voicing) -> float:
    """Total semitones both hands travel, the cost of simply moving.

    Measured at the hand rather than the note: what tires a player is moving
    the hand's anchor, not the individual fingers, so this tracks the lowest
    note of each hand.
    """
    distance = 0.0
    if previous.left and current.left:
        distance += abs(min(current.left) - min(previous.left))
    if previous.right and current.right:
        distance += abs(min(current.right) - min(previous.right))
    return distance


def common_tones(previous: Voicing, current: Voicing) -> int:
    """Pitches held at exactly the same place across the change.

    Holding a note is the cheapest possible voice leading and the main reason
    to invert a chord, so it earns a discount rather than merely avoiding a
    penalty.
    """
    return len(set(previous.pitches) & set(current.pitches))


def explain(previous: Voicing, current: Voicing) -> list[Violation]:
    """Every rule this transition breaks, as reportable objects."""
    return parallels(previous, current) + leaps(previous, current) + overlap(previous, current)


def penalty(previous: Voicing, current: Voicing) -> float:
    """Total rule penalty, without building the explanation.

    Same arithmetic as summing `explain()`, and `test_voiceleading.py` asserts
    they agree on every pair in the corpus. It exists because the solver calls
    this once per edge in the lattice -- hundreds of thousands of times for a
    single arrangement -- and allocating a list of dataclasses each time to add
    up their `penalty` fields dominated the runtime.
    """
    total = 0.0
    before, after = previous.pitches, current.pitches
    n = min(len(before), len(after))

    for i in range(n):
        for j in range(i + 1, n):
            step_i = after[i] - before[i]
            step_j = after[j] - before[j]
            if step_i == 0 or step_j == 0 or (step_i > 0) != (step_j > 0):
                continue
            gap_before = (before[j] - before[i]) % OCTAVE
            if gap_before != (after[j] - after[i]) % OCTAVE:
                continue
            consecutive_fifth = gap_before == PERFECT_FIFTH
            consecutive_octave = gap_before == 0 and (before[j] - before[i]) >= OCTAVE
            if consecutive_fifth or consecutive_octave:
                total += 4.0

    for i in range(n):
        distance = abs(after[i] - before[i])
        limit = 12 if i == n - 1 else 9
        if distance > limit:
            total += 0.5 * (distance - limit)
        if i and after[i] < before[i - 1]:
            total += 1.5
    return total


def transition_cost(previous: Voicing, current: Voicing, level: Level) -> float:
    """What it costs to go from one voicing to the next.

    Rule violations and physical motion are weighted differently by level: an
    advanced arrangement is allowed a parallel fifth inside a dense jazz
    voicing, where it is inaudible, and is expected to move the hands to reach
    a better chord. A beginner arrangement is not.
    """
    cost = level.rule_weight * penalty(previous, current)
    cost += level.motion_weight * 0.25 * motion(previous, current)
    cost -= 0.3 * common_tones(previous, current)
    return cost
