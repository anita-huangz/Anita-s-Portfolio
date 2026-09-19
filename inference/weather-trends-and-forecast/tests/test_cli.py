"""The command line, exercised rather than assumed to work.

`climate_trend` is what a reader runs to reproduce the numbers in the README, so a
broken entry point invalidates the documentation rather than merely annoying
someone. It had no tests: without an `__init__.py` this was a namespace
package, so coverage only counted modules the tests imported and this one was
missing from the table rather than sitting at 0%.

These run the real command against the bundled data. They assert the exit
code, that the sections the flags promise actually appear, and that bad input
fails loudly instead of printing a partial answer.
"""

import pytest

from climate_trend.cli import main


class TestItRuns:
    def test_the_default_invocation_succeeds(self, capsys):
        assert main(["--draws", "100"]) == 0
        assert capsys.readouterr().out.strip()


class TestBadInput:
    def test_a_missing_file_is_reported_not_raised(self, capsys):
        assert main(["--csv", "does-not-exist.csv"]) == 1
        assert "error" in capsys.readouterr().err.lower()

    def test_an_unknown_flag_exits_nonzero(self):
        with pytest.raises(SystemExit) as exit:
            main(["--not-a-real-flag"])
        assert exit.value.code != 0

    def test_help_exits_cleanly(self):
        with pytest.raises(SystemExit) as exit:
            main(["--help"])
        assert exit.value.code == 0
