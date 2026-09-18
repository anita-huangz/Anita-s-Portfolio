"""The request parser, and the boundary the language model is held behind."""

import pytest

from arranger.difficulty import LEVELS
from arranger.intent import STYLES, Intent, apply_style, parse_intent


@pytest.mark.parametrize(
    ("text", "level"),
    [
        ("make it easier", "beginner"),
        ("something simple for a child", "beginner"),
        ("an advanced version", "advanced"),
        ("make it harder", "advanced"),
        ("standard difficulty", "intermediate"),
    ],
)
def test_level_words_are_understood(text, level):
    assert parse_intent(text).level == level


@pytest.mark.parametrize(
    ("text", "style"),
    [
        ("make it jazzy", "jazzy"),
        ("a bluesy feel", "jazzy"),
        ("sparse and quiet", "sparse"),
        ("lush and romantic", "lush"),
        ("like a bach chorale", "hymn"),
    ],
)
def test_style_words_are_understood(text, style):
    assert parse_intent(text).style == style


def test_an_explicit_tempo_beats_a_mood_word():
    # "slow" implies 66; an explicit number must win.
    assert parse_intent("slow, 140 bpm").bpm == 140


def test_mood_words_set_a_tempo():
    assert parse_intent("a sad ballad").bpm < 80
    assert parse_intent("upbeat and energetic").bpm > 110


@pytest.mark.parametrize(
    ("text", "field", "expected"),
    [
        # Both orders of the same pair, so the test cannot pass by accident of
        # dictionary ordering -- which is exactly how it passed before.
        ("easy but actually advanced", "level", "advanced"),
        ("advanced, or actually make it easy", "level", "beginner"),
        ("jazzy but gentle", "style", "sparse"),
        ("gentle but jazzy", "style", "jazzy"),
        ("lush, no, sparse", "style", "sparse"),
        ("sparse, no, lush", "style", "lush"),
    ],
)
def test_the_later_word_in_the_sentence_wins(text, field, expected):
    assert getattr(parse_intent(text), field) == expected


def test_what_it_cannot_parse_is_reported_not_dropped():
    """Silently ignoring half a request is the failure mode to avoid."""
    intent = parse_intent("make it sound like Debussy underwater")
    assert "debussy" in intent.unhandled
    assert intent.level == "intermediate"  # unchanged default


def test_a_fully_understood_request_leaves_nothing_over():
    assert parse_intent("easy jazzy 100 bpm").unhandled == ""


def test_defaults_are_preserved_when_nothing_matches():
    default = Intent(level="advanced", style="lush")
    assert parse_intent("hello there", default).level == "advanced"
    assert parse_intent("hello there", default).style == "lush"


@pytest.mark.parametrize(
    "bad",
    [
        Intent(level="expert"),
        Intent(style="baroque"),
        Intent(bpm=5),
        Intent(bpm=1000),
        Intent(beats_per_chord=0),
        Intent(beats_per_chord=100),
    ],
)
def test_out_of_range_requests_are_rejected(bad):
    """The validator is the whole safety argument for the model layer."""
    with pytest.raises(ValueError):
        bad.validated()


def test_every_style_is_reachable_from_plain_english():
    reachable = {
        parse_intent(phrase).style
        for phrase in ("plain", "jazzy", "sparse", "lush", "hymn")
    }
    assert reachable == set(STYLES)


@pytest.mark.parametrize("style_name", sorted(STYLES))
@pytest.mark.parametrize("level_name", sorted(LEVELS))
def test_applying_a_style_leaves_a_usable_level(level_name, style_name):
    adjusted = apply_style(LEVELS[level_name], STYLES[style_name])
    assert adjusted.max_right_notes >= 2
    assert adjusted.max_span > 0
    assert adjusted.motion_weight >= 0
    assert adjusted.rule_weight >= 0
