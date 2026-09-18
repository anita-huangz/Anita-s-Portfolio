"""The rule engine, checked against textbook examples.

Each test is a case a harmony teacher would recognise, so the rules can be
wrong in an obvious way rather than a subtle one.
"""

import pytest

from arranger.arrange import arrange
from arranger.difficulty import LEVELS
from arranger.theory import parse_chord
from arranger.voiceleading import explain, motion, penalty
from arranger.voicing import Voicing, candidates
from conftest import CORPUS


def V(left, right, symbol="C"):
    return Voicing(left=tuple(left), right=tuple(right), chord=parse_chord(symbol))


def rules(a, b):
    return {v.rule for v in explain(a, b)}


def test_parallel_fifths_are_caught():
    # C4-G4 moving to D4-A4: both voices up a tone, fifth to fifth.
    before = V([], [60, 67])
    after = V([], [62, 69])
    assert "parallel fifths" in rules(before, after)


def test_parallel_octaves_are_caught():
    before = V([], [60, 72])
    after = V([], [62, 74])
    assert "parallel octaves" in rules(before, after)


def test_arriving_at_a_fifth_is_not_the_offence():
    """Only consecutive fifths are barred, not the fifth itself.

    Note what this implies: two voices already a fifth apart cannot reach
    another fifth by contrary motion at all, because holding the interval at
    seven semitones requires both to move by the same amount. So the honest
    test starts from a third, where contrary motion into a fifth is possible.
    """
    # Both voices down a semitone, fifth to fifth: parallel.
    assert "parallel fifths" in rules(V([], [60, 67]), V([], [59, 66]))
    # A major third opening outward to a fifth: contrary motion, allowed.
    assert "parallel fifths" not in rules(V([], [60, 64]), V([], [58, 65]))
    # The same third moving in parallel to a fifth is "direct" motion, which
    # this engine also permits -- only true consecutives are flagged.
    assert "parallel fifths" not in rules(V([], [60, 64]), V([], [62, 69]))


def test_a_held_voice_cannot_make_a_parallel():
    """Parallel motion needs both voices to move. A static one cannot."""
    before = V([], [60, 67])
    after = V([], [60, 67])
    assert not rules(before, after)


def test_repeating_the_same_chord_breaks_no_rules():
    chord = V([48], [60, 64, 67])
    assert explain(chord, chord) == []
    assert penalty(chord, chord) == 0.0


def test_a_large_inner_leap_is_flagged_and_a_melodic_one_is_allowed():
    before = V([], [60, 64, 67])
    # Inner voice jumps a tenth; the limit for an inner voice is a sixth.
    inner = V([], [60, 80, 84])
    assert "large leap" in rules(before, inner)
    # The top voice may leap up to an octave without complaint.
    melody = V([], [60, 64, 76])
    assert "large leap" not in rules(before, melody)


def test_voice_overlap_is_caught():
    before = V([], [60, 67])
    after = V([], [55, 58])  # upper voice falls below where the lower one was
    assert "voice overlap" in rules(before, after)


def test_motion_is_measured_at_the_hand_not_the_note():
    a = V([48], [60, 64, 67])
    b = V([50], [62, 65, 69])
    # Left hand moves 2, right hand's lowest note moves 2.
    assert motion(a, b) == 4


def test_the_fast_penalty_agrees_with_the_explanation_everywhere():
    """`penalty()` exists only for speed; if it ever disagrees it is a bug."""
    level = LEVELS["advanced"]
    checked = 0
    for first, second in [("Cmaj7", "Dm7"), ("G7", "C"), ("Am", "F"), ("Bb7", "Eb")]:
        for a in candidates(parse_chord(first), level)[:30]:
            for b in candidates(parse_chord(second), level)[:30]:
                assert penalty(a, b) == pytest.approx(
                    sum(v.penalty for v in explain(a, b))
                )
                checked += 1
    assert checked >= 3000


def test_a_hymn_arrangement_avoids_parallels_a_jazz_one_tolerates():
    """The rule weight is the point: strict writing should break fewer rules."""
    strict = sum(
        len(arrange(p, "intermediate", "hymn").violations) for p in CORPUS.values()
    )
    loose = sum(
        len(arrange(p, "intermediate", "jazzy").violations) for p in CORPUS.values()
    )
    assert strict <= loose
