"""The command line and the LSTM wrapper, exercised.

Neither had a single test. Coverage did not show it: without an `__init__.py`
this was a namespace package, so `--cov` only counted modules the tests
imported and these two were absent from the table rather than listed at 0%.
The project read 90% and was really 62%.

The LSTM tests deliberately avoid loading the saved model. TensorFlow is an
optional dependency and the weights are an 891 KB artefact, so the suite must
pass without either — `available()` is exactly the seam that makes that
possible, and it is what these check.
"""

import numpy as np
import pytest

from btc_forecast import lstm
from btc_forecast.cli import main

# Enough history for a walk-forward fold without making the suite slow.
FAST = ["--from", "2024-06-01", "--test-size", "60"]


class TestItRuns:
    def test_the_default_invocation_succeeds(self, capsys):
        assert main(FAST) == 0
        assert capsys.readouterr().out.strip()

    @pytest.mark.parametrize(
        "section", ["split", "leakage", "walkforward", "trading"]
    )
    def test_each_section_runs_on_its_own(self, section, capsys):
        assert main([*FAST, "--section", section]) == 0
        assert capsys.readouterr().out.strip()

    def test_the_lstm_section_degrades_rather_than_crashing(self, capsys):
        """TensorFlow may not be installed, and the section must say so."""
        assert main([*FAST, "--section", "lstm"]) == 0
        out = capsys.readouterr().out.lower()
        assert out.strip()
        if not lstm.available():
            assert "tensorflow" in out or "unavailable" in out or "skip" in out


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


class TestLSTMWrapper:
    def test_availability_is_a_plain_boolean(self):
        assert isinstance(lstm.available(), bool)

    def test_availability_is_false_without_the_weights(self, monkeypatch, tmp_path):
        monkeypatch.setattr(lstm, "MODEL", tmp_path / "absent.h5")
        assert lstm.available() is False

    def test_sequences_are_sliding_windows_paired_with_the_next_value(self):
        scaled = np.arange(10, dtype=float).reshape(-1, 1)
        windows, targets = lstm.sequences(scaled, lookback=3)
        assert windows.shape == (7, 3, 1)
        assert targets.shape == (7, 1)
        # Window i must be the three values immediately before target i.
        np.testing.assert_allclose(windows[0].ravel(), [0, 1, 2])
        np.testing.assert_allclose(targets[0], [3])
        np.testing.assert_allclose(windows[-1].ravel(), [6, 7, 8])
        np.testing.assert_allclose(targets[-1], [9])

    def test_a_window_never_contains_its_own_target(self):
        """The leak that would make any forecast look perfect."""
        scaled = np.arange(40, dtype=float).reshape(-1, 1)
        windows, targets = lstm.sequences(scaled, lookback=5)
        for window, target in zip(windows, targets, strict=True):
            assert target[0] not in set(window.ravel().tolist())

    def test_too_short_a_series_yields_no_windows(self):
        windows, targets = lstm.sequences(np.arange(3, dtype=float).reshape(-1, 1), 5)
        assert len(windows) == 0
        assert len(targets) == 0

    def test_the_lookback_matches_the_saved_model(self):
        """90, taken from the model's input shape. The README once said 60."""
        assert lstm.LOOKBACK == 90
