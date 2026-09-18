"""The promise a difficulty level makes, checked over the whole corpus.

"Beginner" is only meaningful if it is never violated. These tests are the
reason the constraints are data rather than prose: a generator that merely
aimed at easiness could not be checked this way.
"""

import pytest

from arranger.arrange import arrange
from arranger.difficulty import LEVELS
from arranger.intent import STYLES, apply_style
from conftest import CORPUS, LEVEL_NAMES, STYLE_NAMES


@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_no_arrangement_ever_exceeds_its_hand_span(progression, level_name):
    level = LEVELS[level_name]
    result = arrange(progression, level_name)
    for step in result.steps:
        assert step.voicing.right_span <= level.max_span, step.chord.symbol
        assert step.voicing.left_span <= level.max_span, step.chord.symbol


@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_no_arrangement_ever_exceeds_its_note_count(progression, level_name):
    level = LEVELS[level_name]
    for step in arrange(progression, level_name).steps:
        assert len(step.voicing.right) <= level.max_right_notes, step.chord.symbol
        assert len(step.voicing.left) <= level.max_left_notes, step.chord.symbol


@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_every_note_is_inside_the_level_register(progression, level_name):
    level = LEVELS[level_name]
    for step in arrange(progression, level_name).steps:
        assert all(level.left_low <= p <= level.left_high for p in step.voicing.left)
        assert all(level.right_low <= p <= level.right_high for p in step.voicing.right)


@pytest.mark.parametrize("style_name", STYLE_NAMES)
@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_a_style_can_never_loosen_a_level(progression, level_name, style_name):
    """The bug this is here for: "jazzy" once bought a beginner a fourth note."""
    level = LEVELS[level_name]
    for step in arrange(progression, level_name, style_name).steps:
        assert len(step.voicing.right) <= level.max_right_notes
        assert len(step.voicing.left) <= level.max_left_notes
        assert step.voicing.span <= level.max_span


@pytest.mark.parametrize("style_name", STYLE_NAMES)
@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_apply_style_never_raises_a_hard_limit(level_name, style_name):
    level = LEVELS[level_name]
    adjusted = apply_style(level, STYLES[style_name])
    assert adjusted.max_span <= level.max_span
    assert adjusted.max_right_notes <= level.max_right_notes
    assert adjusted.max_left_notes <= level.max_left_notes
    # An extension-hungry style still cannot unlock extensions at a level that
    # forbids them.
    assert adjusted.allow_extensions <= level.allow_extensions


def test_beginner_never_plays_an_extension():
    result = arrange("Cmaj9 Dm11 G13 Cmaj7", "beginner")
    for step in result.steps:
        sounded = {p % 12 for p in step.voicing.pitches}
        # Every sounding pitch class must belong to the plain seventh chord.
        allowed = {
            (step.chord.root + i) % 12
            for i in step.chord.intervals
            if i <= 11
        }
        assert sounded <= allowed, f"{step.chord.symbol} played {sorted(sounded - allowed)}"


def test_beginner_keeps_the_root_in_the_bass():
    result = arrange("C G/B Am F", "beginner")
    for step in result.steps:
        assert step.voicing.bass % 12 == step.chord.root % 12


def test_intermediate_honours_a_written_slash_bass():
    result = arrange("C G/B Am/G F", "intermediate")
    for step in result.steps:
        if step.chord.is_slash:
            assert step.voicing.bass % 12 == step.chord.bass % 12, step.chord.symbol


def test_simplifications_are_reported_not_hidden():
    result = arrange("Cmaj9 G7/B", "beginner")
    assert result.simplifications, "a beginner must be told what was dropped"
    reasons = " ".join(note for _, note in result.simplifications)
    assert "9th" in reasons
    assert "root position" in reasons


def test_an_advanced_arrangement_simplifies_nothing_it_can_play():
    assert arrange("Cmaj9 Dm11 G13", "advanced").simplifications == []


@pytest.mark.parametrize("level_name", LEVEL_NAMES)
def test_every_corpus_chord_can_be_voiced_at_every_level(level_name):
    """No hole in any arrangement: every chord gets a playable voicing."""
    for name, progression in CORPUS.items():
        result = arrange(progression, level_name)
        assert len(result.steps) == len(progression.split()), name
        assert all(step.voicing.pitches for step in result.steps), name
