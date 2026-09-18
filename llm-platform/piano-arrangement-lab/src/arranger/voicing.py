"""Candidate voicings for one chord, under one difficulty level.

A chord symbol says which notes, never which octaves — "Cmaj7" is four pitch
classes, and there are hundreds of ways two hands can play it. This module
enumerates the ones a hand can physically reach at a given level, and scores
each on how comfortable it is in isolation.

Comfort in isolation is only half the problem. A voicing that is lovely on its
own may be unreachable from the previous chord, which is why this module scores
each candidate but does not choose between them: choosing is a path problem
over the whole progression, and `arrange.py` solves it.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property, lru_cache
from itertools import combinations, pairwise
from typing import TYPE_CHECKING

from .difficulty import Level
from .theory import DEGREE_OF_INTERVAL, Chord

if TYPE_CHECKING:  # pragma: no cover - import cycle only matters to type checkers
    from .intent import Style

#: Hard ceiling on candidates kept per chord. The dynamic program is quadratic
#: in this, so it is the dial between arrangement quality and speed. Candidates
#: are ranked by static cost before truncation, so what survives is the
#: comfortable end of the list.
#:
#: 60 is measured, not guessed. Across the eight-progression corpus at three
#: levels and five styles -- 120 arrangements -- a cap of 60 produces byte-for-
#: byte the same result as a cap of 200, seven times faster. It degrades from
#: 40 down: 25 costs 0.08% and is worse on 8 of the 120, and 8 costs 3.3%.
#: `test_arrange.py::test_the_candidate_cap_is_not_binding` re-checks the
#: lossless claim, so lowering this carelessly fails the suite rather than
#: quietly producing worse arrangements.
MAX_CANDIDATES = 60

#: Where a piano left hand normally sits: roughly E1 to C3. Outside this the
#: instrument either rumbles indistinctly or stops sounding like an accompaniment.
BASS_LOW = 28
BASS_HIGH = 48


@dataclass(frozen=True)
class Simplified:
    """A chord as a level can actually play it, and what was given up.

    Simplification happens once, here, so that the cost function and the
    candidate generator cannot disagree about which chord they are scoring --
    an earlier version penalised a voicing for omitting a bass note that the
    generator had already, deliberately, decided to drop.

    `notes` is surfaced to the player rather than swallowed. Being told "the
    13th was dropped at this level" is useful; silently playing a different
    chord is not.
    """

    chord: Chord
    notes: tuple[str, ...] = ()

    @property
    def simplified(self) -> bool:
        return bool(self.notes)


def simplify(chord: Chord, level: Level) -> Simplified:
    """Reduce a chord to what this level can play, reporting each reduction."""
    notes: list[str] = []
    intervals = chord.intervals
    bass = chord.bass

    if not level.allow_extensions:
        kept = tuple(
            i for i in intervals
            if DEGREE_OF_INTERVAL.get(i % 24) not in {"9th", "11th", "13th"}
        )
        if kept != intervals:
            dropped = sorted(
                {DEGREE_OF_INTERVAL.get(i % 24, "?") for i in intervals if i not in kept}
            )
            notes.append(f"dropped the {', '.join(dropped)}")
            intervals = kept

    # A slash chord *is* an inversion, so a level that forbids inversions
    # cannot play one. Dropping the alternate bass keeps the chord sounding in
    # its plainest form rather than leaving a hole in the arrangement.
    if chord.is_slash and not level.allow_inversions:
        notes.append("played in root position instead of over the written bass")
        bass = None

    if not notes:
        return Simplified(chord)
    return Simplified(
        Chord(chord.symbol, chord.root, chord.quality, intervals, bass),
        tuple(notes),
    )


@dataclass(frozen=True)
class Voicing:
    """One way to play one chord: pitches for each hand."""

    left: tuple[int, ...]
    right: tuple[int, ...]
    chord: Chord

    @cached_property
    def pitches(self) -> tuple[int, ...]:
        """Every sounding pitch, low to high.

        Cached because the solver reads it inside its inner loop: profiling a
        seven-chord advanced arrangement showed 3.7 million calls, each
        re-sorting the same five integers, for about a fifth of total runtime.
        """
        return tuple(sorted(self.left + self.right))

    @property
    def bass(self) -> int:
        return min(self.pitches)

    @property
    def melody(self) -> int:
        """Top note. The line a listener actually follows."""
        return max(self.pitches)

    @property
    def right_span(self) -> int:
        return max(self.right) - min(self.right) if len(self.right) > 1 else 0

    @property
    def left_span(self) -> int:
        return max(self.left) - min(self.left) if len(self.left) > 1 else 0

    @property
    def span(self) -> int:
        return max(self.right_span, self.left_span)

    def __len__(self) -> int:
        return len(self.left) + len(self.right)


def _pitches_in(pitch_classes: set[int], low: int, high: int) -> list[int]:
    return [p for p in range(low, high + 1) if p % 12 in pitch_classes]


def static_cost(voicing: Voicing, level: Level, style: Style | None = None) -> float:
    """How awkward this voicing is on its own, ignoring what came before.

    Every term is a real ergonomic or acoustic complaint, not a tuning knob:
    stretched hands tire, muddy low intervals sound like mud, and a voicing
    with a gaping hole in the middle sounds hollow.
    """
    cost = 0.0

    # Stretch, counted against a comfortable rather than a maximum hand.
    comfortable = 9  # a major sixth
    for span in (voicing.right_span, voicing.left_span):
        if span > comfortable:
            cost += 0.8 * (span - comfortable)

    # Low intervals below roughly F#3 turn to mud: the harmonics of two close
    # low notes overlap enough to beat against each other. Engravers avoid
    # thirds below the bass clef staff for exactly this reason.
    pitches = voicing.pitches
    for a, b in pairwise(pitches):
        if b < 54 and (b - a) < 7:
            cost += 1.5 * (7 - (b - a)) / 7

    # A hole between the hands leaves the chord sounding hollow.
    if voicing.left and voicing.right:
        gap = min(voicing.right) - max(voicing.left)
        if gap > 16:
            cost += 0.4 * (gap - 16)

    # A chord tone that is simply absent. The fifth is cheap to drop -- it is
    # implied by the root and says nothing about quality, which is why shell
    # voicings omit it -- but a missing third or seventh makes this a different
    # chord, and a missing root leaves it rootless, which only works in a band.
    sounded = {p % 12 for p in pitches}
    for interval in voicing.chord.intervals:
        pc = (voicing.chord.root + interval) % 12
        if pc in sounded:
            continue
        degree = DEGREE_OF_INTERVAL.get(interval % 24, "")
        fifth_penalty = 0.6 if style is None else style.fifth_penalty
        colour = 0.3 if style is None else style.extension_penalty
        cost += {
            "5th": fifth_penalty, "9th": colour, "11th": colour, "13th": colour
        }.get(degree, 3.0)

    # Prefer the root, or the written bass when the chord asks for one.
    wanted_bass = voicing.chord.bass if voicing.chord.bass is not None else voicing.chord.root
    if voicing.bass % 12 != wanted_bass % 12:
        cost += 2.5 if voicing.chord.is_slash else 1.0

    # More notes is more to coordinate; mild, so richness is not forbidden.
    cost += 0.15 * max(0, len(voicing) - 3)

    if style is not None:
        # A style nudges preferences; it never relaxes a hard constraint, so a
        # "jazzy" beginner arrangement is still inside a beginner's hand.
        # Distance from a target rather than a per-note reward, so the cost
        # stays non-negative and totals remain comparable between styles.
        cost += style.density_weight * abs(len(voicing.right) - style.target_density)

    # Keep the bass where a piano bass lives. Without this the solver is free
    # to float the whole texture upward -- every other term is relative, so a
    # voicing an octave too high scores identically to one in place, and ties
    # were being broken by enumeration order rather than by musical sense.
    bass = voicing.bass
    if bass > BASS_HIGH:
        cost += 0.35 * (bass - BASS_HIGH)
    elif bass < BASS_LOW:
        cost += 0.35 * (BASS_LOW - bass)

    # Keep the melody in a singable register rather than shrieking at the top.
    if voicing.melody > level.right_high - 2:
        cost += 0.5 * (voicing.melody - (level.right_high - 2))
    return cost


@lru_cache(maxsize=512)
def candidates(
    chord: Chord, level: Level, style: Style | None = None
) -> tuple[Voicing, ...]:
    """Every playable voicing of this chord at this level, best-first.

    Cached: progressions repeat chords constantly -- a twelve-bar blues names
    four -- and enumerating a chord's voicings is the same work every time.
    Both arguments are frozen dataclasses, so they hash by value and two
    separately parsed `Cmaj7`s share an entry. A tuple is returned rather than
    a list so a caller cannot mutate what the next caller receives.

    Raises if the chord cannot be voiced at all at this level, which is a real
    outcome worth surfacing rather than silently returning an empty list and
    producing a hole in the arrangement.
    """
    chord = simplify(chord, level).chord
    intervals = chord.intervals
    pcs = {(chord.root + i) % 12 for i in intervals}
    essential = {(chord.root + i) % 12 for i in chord.essential if i in intervals}
    bass_pc = (chord.bass if chord.bass is not None else chord.root) % 12

    left_options: list[tuple[int, ...]] = []
    for root_pitch in _pitches_in({bass_pc}, level.left_low, level.left_high):
        left_options.append((root_pitch,))
        if level.max_left_notes >= 2:
            for other in _pitches_in(pcs - {bass_pc}, root_pitch + 3, root_pitch + level.max_span):
                left_options.append((root_pitch, other))
        if level.max_left_notes >= 3:
            for a, b in combinations(
                _pitches_in(pcs, root_pitch + 3, root_pitch + level.max_span), 2
            ):
                left_options.append((root_pitch, a, b))

    right_pool = _pitches_in(pcs, level.right_low, level.right_high)
    right_options: list[tuple[int, ...]] = []
    for size in range(2, level.max_right_notes + 1):
        for combo in combinations(right_pool, size):
            if combo[-1] - combo[0] > level.max_span:
                continue
            if not essential.issubset({p % 12 for p in combo}):
                continue
            right_options.append(combo)

    out: list[Voicing] = []
    for left in left_options:
        for right in right_options:
            if right[0] <= left[-1]:
                continue  # hands must not cross or collide
            voicing = Voicing(left=left, right=right, chord=chord)
            out.append(voicing)

    if not out:
        raise ValueError(
            f"{chord.symbol} cannot be voiced at the {level.name} level "
            f"(needs {sorted(essential)} within a {level.max_span}-semitone span)"
        )
    # Ranked under the same objective the solver will use, style included.
    # Ranking without the style and then optimising with it truncated away the
    # voicings the style actually wanted -- a "sparse" arrangement was chosen
    # from the 60 voicings that were best for *plain*.
    out.sort(key=lambda v: static_cost(v, level, style))
    return tuple(out[:MAX_CANDIDATES])
