"""The command line, exercised rather than assumed to work.

`arrange` is what the README's worked example runs, so a broken entry point
invalidates the documentation. It was the largest untested module in the
project at 98 statements.
"""

import pytest

from arranger.cli import main

CHORDS = "Dm7 G7 Cmaj7"


class TestItRuns:
    @pytest.mark.parametrize("level", ["beginner", "intermediate", "advanced"])
    def test_every_level_arranges(self, level, capsys):
        assert main([CHORDS, "--level", level, "--no-keyboard"]) == 0
        out = capsys.readouterr().out
        assert level.upper() in out
        for chord in CHORDS.split():
            assert chord in out

    @pytest.mark.parametrize("style", ["plain", "jazzy", "sparse", "lush", "hymn"])
    def test_every_style_arranges(self, style, capsys):
        assert main([CHORDS, "--style", style, "--no-keyboard"]) == 0
        assert capsys.readouterr().out.strip()

    def test_compare_prints_all_three_levels(self, capsys):
        assert main([CHORDS, "--compare", "--no-keyboard"]) == 0
        out = capsys.readouterr().out
        for level in ("BEGINNER", "INTERMEDIATE", "ADVANCED"):
            assert level in out

    def test_greedy_runs_and_says_it_is_not_exact(self, capsys):
        assert main([CHORDS, "--greedy", "--no-keyboard"]) == 0
        greedy = capsys.readouterr().out
        assert main([CHORDS, "--no-keyboard"]) == 0
        exact = capsys.readouterr().out
        # The solver reports how many transitions it evaluated; greedy does not.
        assert "transitions evaluated" in exact
        assert "transitions evaluated" not in greedy

    def test_the_keyboard_is_drawn_by_default(self, capsys):
        assert main([CHORDS]) == 0
        assert "|" in capsys.readouterr().out


class TestNaturalLanguage:
    def test_it_reads_a_described_request(self, capsys):
        assert main([CHORDS, "--describe", "an easy sparse version", "--no-keyboard"]) == 0
        out = capsys.readouterr().out
        assert "beginner" in out and "sparse" in out

    def test_it_reports_what_it_could_not_understand(self, capsys):
        assert main([CHORDS, "--describe", "like Debussy underwater", "--no-keyboard"]) == 0
        assert "not understood" in capsys.readouterr().out

    def test_without_a_provider_it_says_keywords_did_the_work(self, capsys):
        assert main([CHORDS, "--describe", "make it jazzy", "--no-keyboard"]) == 0
        assert "[keywords]" in capsys.readouterr().out


class TestMidi:
    def test_it_writes_a_playable_file(self, tmp_path, capsys):
        out = tmp_path / "out.mid"
        assert main([CHORDS, "--midi", str(out), "--no-keyboard"]) == 0
        assert out.exists()
        # A header chunk, its declared length, and at least one track.
        data = out.read_bytes()
        assert data[:4] == b"MThd"
        assert b"MTrk" in data
        assert f"wrote {out}" in capsys.readouterr().out


class TestBadInput:
    def test_an_unreadable_chord_is_reported_not_raised(self, capsys):
        assert main(["C H7", "--no-keyboard"]) == 1
        assert "error" in capsys.readouterr().err.lower()

    def test_an_empty_progression_is_reported(self, capsys):
        assert main(["   ", "--no-keyboard"]) == 1
        assert "error" in capsys.readouterr().err.lower()

    def test_an_unknown_level_exits_nonzero(self):
        with pytest.raises(SystemExit) as exit:
            main([CHORDS, "--level", "expert"])
        assert exit.value.code != 0

    def test_help_exits_cleanly(self):
        with pytest.raises(SystemExit) as exit:
            main(["--help"])
        assert exit.value.code == 0
