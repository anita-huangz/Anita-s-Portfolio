import pytest

from arranger.theory import (
    QUALITIES,
    Chord,
    ChordError,
    note_name,
    parse_chord,
    parse_note,
    parse_progression,
)


@pytest.mark.parametrize("quality", sorted(QUALITIES))
def test_every_quality_parses_and_keeps_its_intervals(quality):
    chord = parse_chord(f"C{quality}")
    assert chord.intervals == QUALITIES[quality]
    assert chord.root == 0


@pytest.mark.parametrize(
    ("text", "midi"),
    [("C4", 60), ("C-1", 0), ("A0", 21), ("C8", 108), ("Bb3", 58), ("F#5", 78)],
)
def test_note_names_round_trip(text, midi):
    assert parse_note(text) == midi
    # Names come back sharp-spelled, so only compare where that is the spelling.
    assert parse_note(note_name(midi)) == midi


def test_enharmonics_are_the_same_key():
    assert parse_note("F#4") == parse_note("Gb4")
    assert parse_chord("C#").root == parse_chord("Db").root


def test_longest_quality_wins():
    # "maj7" must not be read as "maj" with leftovers, nor "m7b5" as "m7".
    assert parse_chord("Cmaj7").intervals == (0, 4, 7, 11)
    assert parse_chord("Cm7b5").intervals == (0, 3, 6, 10)
    assert parse_chord("Cm7").intervals == (0, 3, 7, 10)


def test_slash_chords_carry_a_bass():
    chord = parse_chord("G7/B")
    assert chord.root == 7
    assert chord.bass == 11
    assert chord.is_slash


def test_a_slash_naming_the_root_is_not_an_inversion():
    assert not parse_chord("C/C").is_slash


def test_essential_tones_are_the_third_and_seventh():
    # The fifth is droppable; the third defines the quality.
    assert parse_chord("Cmaj7").essential == (0, 4, 11)
    assert parse_chord("Cm7").essential == (0, 3, 10)
    # A sus chord has no third, so the fourth is what must be kept.
    assert parse_chord("Csus4").essential == (0, 5)


def test_pitch_classes_are_deduplicated_and_sorted():
    assert parse_chord("C9").pitch_classes == (0, 2, 4, 7, 10)


@pytest.mark.parametrize("bad", ["", "H", "Cmaj77", "C#$", "  ", "Xm7"])
def test_unreadable_symbols_say_so(bad):
    with pytest.raises(ChordError):
        parse_chord(bad)


def test_progressions_split_on_bars_and_commas():
    assert [c.symbol for c in parse_progression("C Am | F, G7")] == ["C", "Am", "F", "G7"]


def test_an_empty_progression_is_an_error():
    with pytest.raises(ChordError):
        parse_progression("   ")


def test_chord_is_hashable_so_it_can_key_a_cache():
    assert isinstance(hash(parse_chord("Cmaj7")), int)
    assert isinstance(parse_chord("C"), Chord)
