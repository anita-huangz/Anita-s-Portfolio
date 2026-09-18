"""Choosing one voicing per chord, optimally, over the whole progression.

This is the part that makes the project more than a chord dictionary. Picking
the nicest voicing for each chord independently gives a bad arrangement,
because "nicest" depends entirely on what came before: a lovely Cmaj7 that
forces the hand to jump a tenth to reach the next chord is the wrong Cmaj7.

Written out, the problem is a shortest path. Each chord contributes a layer of
candidate voicings; each candidate has a static cost; each pair of candidates in
adjacent layers has a transition cost. The best arrangement is the cheapest path
through that lattice, and the Viterbi recurrence finds it exactly in
O(n * k^2) rather than the k^n a naive search would take.

Exactly matters. A greedy pass -- take the best first chord, then the best
follower, and so on -- is what most arrangers do and it is wrong: it cannot
accept a slightly worse voicing now to avoid a much worse one later.
`test_arrange.py` checks the solver against brute force on short progressions
and against a greedy baseline on long ones, so the claim is measured.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .difficulty import LEVELS, Level
from .intent import STYLES, Style, apply_style
from .theory import Chord, parse_progression
from .voiceleading import Violation, explain, transition_cost
from .voicing import Simplified, Voicing, candidates, simplify, static_cost


@dataclass(frozen=True)
class Step:
    """One chord in the finished arrangement."""

    chord: Chord
    voicing: Voicing
    #: What was given up to make this chord playable at this level.
    notes: tuple[str, ...] = ()
    #: Rules broken moving into this chord from the previous one.
    violations: tuple[Violation, ...] = ()
    static: float = 0.0
    transition: float = 0.0

    @property
    def cost(self) -> float:
        return self.static + self.transition


@dataclass(frozen=True)
class Arrangement:
    """The finished arrangement and the evidence for it."""

    level: Level
    style: Style | None = None
    steps: list[Step] = field(default_factory=list)
    total_cost: float = 0.0
    #: Candidate voicings considered per chord, and paths implied by them.
    searched: int = 0

    @property
    def chords(self) -> list[Chord]:
        return [s.chord for s in self.steps]

    @property
    def violations(self) -> list[Violation]:
        return [v for s in self.steps for v in s.violations]

    @property
    def simplifications(self) -> list[tuple[str, str]]:
        return [(s.chord.symbol, n) for s in self.steps for n in s.notes]

    @property
    def max_span(self) -> int:
        return max((s.voicing.span for s in self.steps), default=0)

    @property
    def total_motion(self) -> int:
        """Semitones the hands travel across the whole piece."""
        total = 0
        for before, after in zip(self.steps, self.steps[1:], strict=False):
            if before.voicing.left and after.voicing.left:
                total += abs(min(after.voicing.left) - min(before.voicing.left))
            if before.voicing.right and after.voicing.right:
                total += abs(min(after.voicing.right) - min(before.voicing.right))
        return total


def _resolve(
    chords: list[Chord] | str, level: Level | str, style: Style | str | None
) -> tuple[list[Chord], Level, Style]:
    if isinstance(chords, str):
        chords = parse_progression(chords)
    if isinstance(level, str):
        if level not in LEVELS:
            raise ValueError(f"unknown level {level!r}; try one of {sorted(LEVELS)}")
        level = LEVELS[level]
    if style is None:
        style = STYLES["plain"]
    elif isinstance(style, str):
        if style not in STYLES:
            raise ValueError(f"unknown style {style!r}; try one of {sorted(STYLES)}")
        style = STYLES[style]
    if not chords:
        raise ValueError("no chords to arrange")
    return chords, apply_style(level, style), style


def arrange(
    chords: list[Chord] | str,
    level: Level | str = "intermediate",
    style: Style | str | None = None,
) -> Arrangement:
    """Solve for the cheapest playable path through the progression."""
    chords, level, style = _resolve(chords, level, style)

    layers: list[tuple[Voicing, ...]] = []
    simplifications: list[Simplified] = []
    for chord in chords:
        simplifications.append(simplify(chord, level))
        layers.append(candidates(chord, level))

    # Viterbi forward pass. `best[i]` is the cost of the cheapest path ending
    # at candidate i of the current layer; `came_from[i]` is the candidate in
    # the previous layer that path came through.
    best = [static_cost(v, level, style) for v in layers[0]]
    back: list[list[int]] = []
    searched = len(layers[0])

    for depth in range(1, len(layers)):
        previous_layer, layer = layers[depth - 1], layers[depth]
        scores = [float("inf")] * len(layer)
        came_from = [0] * len(layer)
        for j, current in enumerate(layer):
            own = static_cost(current, level, style)
            for i, previous in enumerate(previous_layer):
                total = best[i] + own + transition_cost(previous, current, level)
                if total < scores[j]:
                    scores[j] = total
                    came_from[j] = i
        searched += len(previous_layer) * len(layer)
        best, _ = scores, None
        back.append(came_from)

    # Walk the pointers back from the cheapest endpoint.
    end = min(range(len(best)), key=best.__getitem__)
    total = best[end]
    path = [end]
    for came_from in reversed(back):
        path.append(came_from[path[-1]])
    path.reverse()

    steps: list[Step] = []
    for depth, index in enumerate(path):
        voicing = layers[depth][index]
        previous = layers[depth - 1][path[depth - 1]] if depth else None
        steps.append(Step(
            chord=chords[depth],
            voicing=voicing,
            notes=simplifications[depth].notes,
            violations=tuple(explain(previous, voicing)) if previous else (),
            static=static_cost(voicing, level, style),
            transition=transition_cost(previous, voicing, level) if previous else 0.0,
        ))

    return Arrangement(
        level=level, style=style, steps=steps, total_cost=total, searched=searched
    )


def arrange_greedy(
    chords: list[Chord] | str,
    level: Level | str = "intermediate",
    style: Style | str | None = None,
) -> Arrangement:
    """The obvious approach, kept so the solver can be measured against it.

    Take the cheapest first voicing, then at each step the cheapest follower.
    This is what an arranger written in an afternoon does, and it is not merely
    inelegant -- it produces measurably worse arrangements, because it cannot
    trade a small loss now for a larger saving later.
    """
    chords, level, style = _resolve(chords, level, style)

    steps: list[Step] = []
    total = 0.0
    previous: Voicing | None = None
    for chord in chords:
        layer = candidates(chord, level)
        if previous is None:
            chosen = min(layer, key=lambda v: static_cost(v, level, style))
            step_cost = static_cost(chosen, level, style)
            transition = 0.0
        else:
            chosen = min(
                layer,
                key=lambda v: static_cost(v, level, style)
                + transition_cost(previous, v, level),
            )
            transition = transition_cost(previous, chosen, level)
            step_cost = static_cost(chosen, level, style) + transition
        total += step_cost
        steps.append(Step(
            chord=chord,
            voicing=chosen,
            notes=simplify(chord, level).notes,
            violations=tuple(explain(previous, chosen)) if previous else (),
            static=static_cost(chosen, level, style),
            transition=transition,
        ))
        previous = chosen
    return Arrangement(level=level, style=style, steps=steps, total_cost=total)
