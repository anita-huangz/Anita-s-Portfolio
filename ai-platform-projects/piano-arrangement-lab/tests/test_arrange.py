"""The claim that makes this more than a chord dictionary: the path is optimal.

An arranger that says "I pick good voicings" cannot be checked. One that says
"I return the minimum-cost path through the lattice" can be, by enumerating
every path on a small problem and confirming nothing is cheaper.
"""

from itertools import pairwise, product

import pytest

import arranger.voicing as voicing_module
from arranger.arrange import arrange, arrange_greedy
from arranger.difficulty import LEVELS
from arranger.intent import STYLES, apply_style
from arranger.theory import parse_progression
from arranger.voiceleading import transition_cost
from arranger.voicing import candidates, static_cost
from conftest import CORPUS, LEVEL_NAMES, STYLE_NAMES


def brute_force(progression: str, level_name: str, cap: int = 12) -> float:
    """Cheapest path, found by trying all of them.

    Exponential, so it is only usable on a few chords with a small candidate
    cap -- which is exactly the point: this is the definition the fast solver
    has to agree with.
    """
    level = apply_style(LEVELS[level_name], STYLES["plain"])
    style = STYLES["plain"]
    layers = [candidates(c, level)[:cap] for c in parse_progression(progression)]
    best = float("inf")
    for path in product(*layers):
        total = sum(static_cost(v, level, style) for v in path)
        total += sum(
            transition_cost(a, b, level) for a, b in pairwise(path)
        )
        best = min(best, total)
    return best


@pytest.mark.parametrize("level_name", LEVEL_NAMES)
@pytest.mark.parametrize(
    "progression",
    ["C Am F", "Dm7 G7 Cmaj7", "F#m7b5 B7 Em", "C G/B Am"],
)
def test_the_solver_matches_brute_force(progression, level_name, monkeypatch):
    """Three chords, twelve candidates each: 1,728 paths, all enumerated."""
    monkeypatch.setattr(voicing_module, "MAX_CANDIDATES", 12)
    voicing_module.candidates.cache_clear()
    try:
        expected = brute_force(progression, level_name, cap=12)
        assert arrange(progression, level_name).total_cost == pytest.approx(expected)
    finally:
        voicing_module.candidates.cache_clear()


@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_the_solver_is_never_worse_than_greedy(progression, level_name):
    optimal = arrange(progression, level_name)
    greedy = arrange_greedy(progression, level_name)
    assert optimal.total_cost <= greedy.total_cost + 1e-9


def test_the_solver_is_measurably_better_than_greedy():
    """Not merely 'never worse' -- better, by an amount worth reporting.

    The numbers in the README come from this. Greedy cannot trade a small loss
    now for a larger saving later, and on real progressions that costs it.
    """
    margins = {}
    for level_name in LEVEL_NAMES:
        optimal = sum(arrange(p, level_name).total_cost for p in CORPUS.values())
        greedy = sum(arrange_greedy(p, level_name).total_cost for p in CORPUS.values())
        margins[level_name] = (greedy - optimal) / optimal
    assert margins["beginner"] > 0.03
    assert margins["intermediate"] > 0.05
    assert margins["advanced"] > 0.20


def test_the_candidate_cap_is_not_binding(progression):
    """Raising the cap must not find a better path, or 60 was too low.

    This is the guard on the measurement recorded in `voicing.MAX_CANDIDATES`.
    """
    for level_name in LEVEL_NAMES:
        tight = arrange(progression, level_name).total_cost
        voicing_module.candidates.cache_clear()
        original = voicing_module.MAX_CANDIDATES
        voicing_module.MAX_CANDIDATES = 200
        try:
            voicing_module.candidates.cache_clear()
            generous = arrange(progression, level_name).total_cost
        finally:
            voicing_module.MAX_CANDIDATES = original
            voicing_module.candidates.cache_clear()
        assert tight == pytest.approx(generous, abs=1e-9), level_name


@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_every_chord_gets_exactly_one_voicing(progression, level_name):
    chords = parse_progression(progression)
    result = arrange(progression, level_name)
    assert [s.chord.symbol for s in result.steps] == [c.symbol for c in chords]


def test_the_reported_total_equals_the_sum_of_the_steps(progression):
    result = arrange(progression, "intermediate")
    assert result.total_cost == pytest.approx(sum(s.cost for s in result.steps))


@pytest.mark.parametrize("style_name", STYLE_NAMES)
def test_every_style_produces_a_playable_arrangement(progression, style_name):
    result = arrange(progression, "intermediate", style_name)
    assert len(result.steps) == len(progression.split())
    assert result.total_cost >= 0, "a style must not drive the objective negative"


def test_sparse_really_is_sparser_than_lush():
    for level_name in ("intermediate", "advanced"):
        sparse = arrange(CORPUS["ii-V-I"], level_name, "sparse")
        lush = arrange(CORPUS["ii-V-I"], level_name, "lush")
        sparse_notes = sum(len(s.voicing) for s in sparse.steps)
        lush_notes = sum(len(s.voicing) for s in lush.steps)
        assert sparse_notes < lush_notes, level_name


def test_a_harder_level_is_never_forced_into_a_worse_arrangement():
    """Advanced has every option beginner has, so it cannot do worse.

    Compared on a common yardstick -- the plain-style cost at the *advanced*
    weighting -- because each level scores itself differently and the totals
    are not otherwise comparable.
    """
    for progression in CORPUS.values():
        level = LEVELS["advanced"]
        style = STYLES["plain"]

        def score(result, level=level, style=style):
            total = sum(static_cost(s.voicing, level, style) for s in result.steps)
            total += sum(
                transition_cost(a.voicing, b.voicing, level)
                for a, b in pairwise(result.steps)
            )
            return total

        assert score(arrange(progression, "advanced")) <= score(
            arrange(progression, "beginner")
        ) + 1e-9


def test_unknown_level_and_style_are_rejected():
    with pytest.raises(ValueError, match="unknown level"):
        arrange("C", "expert")
    with pytest.raises(ValueError, match="unknown style"):
        arrange("C", "beginner", "baroque")


def test_a_single_chord_arranges():
    result = arrange("Cmaj7", "intermediate")
    assert len(result.steps) == 1
    assert result.steps[0].transition == 0.0
    assert not result.violations


def test_an_empty_progression_is_an_error():
    with pytest.raises(ValueError):
        arrange([], "beginner")
