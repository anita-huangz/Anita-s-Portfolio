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

import builtins
import sys
import types

import numpy as np
import pandas as pd
import pytest

from btc_forecast import lstm
from btc_forecast.cli import main
from btc_forecast.data import build_daily_from_minutes, load

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


class TestTensorFlowIsGenuinelyOptional:
    """`available()` is the seam. It has to be right in both directions."""

    def test_a_missing_tensorflow_is_reported_not_raised(self, monkeypatch, tmp_path):
        # CI has no TensorFlow, so this is the branch that actually runs there.
        model = tmp_path / "model.keras"
        model.write_bytes(b"not really a model")
        monkeypatch.setattr(lstm, "MODEL", model)

        real_import = builtins.__import__

        def no_tensorflow(name, *args, **kwargs):
            if name == "tensorflow":
                raise ImportError("No module named 'tensorflow'")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", no_tensorflow)
        assert lstm.available() is False

    def test_the_model_file_is_checked_before_the_import_is_attempted(
        self, monkeypatch, tmp_path
    ):
        # Importing TensorFlow costs seconds. Checking for a file that is not
        # there first means the common case never pays for it.
        monkeypatch.setattr(lstm, "MODEL", tmp_path / "absent.keras")

        def refuse(name, *args, **kwargs):
            raise AssertionError(f"imported {name} before checking for the model")

        monkeypatch.setattr(builtins, "__import__", refuse)
        assert lstm.available() is False


class TestRebuildingTheDailyBars:
    """The committed CSV is reproducible, and the test proves it on a small one.

    The real minute file is 127 MB and not in the repo, but the reduction is
    ordinary resampling, so a synthetic two-day file exercises the same path.
    """

    @staticmethod
    def minute_file(path, rows):
        import zstandard

        frame = pd.DataFrame(rows)
        compressor = zstandard.ZstdCompressor()
        path.write_bytes(compressor.compress(frame.to_csv(index=False).encode()))
        return path

    @staticmethod
    def two_days():
        # 08:00 and 12:00 on two consecutive days, so first/last are unambiguous.
        stamps = [
            pd.Timestamp("2024-01-01 08:00", tz="UTC"),
            pd.Timestamp("2024-01-01 12:00", tz="UTC"),
            pd.Timestamp("2024-01-02 08:00", tz="UTC"),
            pd.Timestamp("2024-01-02 12:00", tz="UTC"),
        ]
        return {
            "Timestamp": [int(s.timestamp()) for s in stamps],
            "Open": [10.0, 12.0, 20.0, 22.0],
            "High": [15.0, 13.0, 25.0, 23.0],
            "Low": [9.0, 11.0, 19.0, 21.0],
            "Close": [12.0, 14.0, 22.0, 24.0],
            "Volume": [1.0, 2.0, 3.0, 4.0],
        }

    def test_minutes_reduce_to_one_bar_a_day_with_the_right_aggregation(self, tmp_path):
        source = self.minute_file(tmp_path / "minutes.csv.zstd", self.two_days())
        prices = build_daily_from_minutes(source, tmp_path / "daily.csv")

        frame = prices.frame
        assert len(frame) == 2
        # Open is the day's first minute, Close its last, High/Low the extremes,
        # Volume the sum -- getting any of these from the wrong end silently
        # shifts every return computed downstream.
        assert list(frame["Open"]) == [10.0, 20.0]
        assert list(frame["Close"]) == [14.0, 24.0]
        assert list(frame["High"]) == [15.0, 25.0]
        assert list(frame["Low"]) == [9.0, 19.0]
        assert list(frame["Volume"]) == [3.0, 7.0]

    def test_the_written_csv_names_its_date_column(self, tmp_path):
        # Assigning `.date` replaces the index and drops its name, so naming it
        # afterwards is what keeps the first header cell from being blank --
        # and a blank one makes the CSV unreadable by `load`.
        source = self.minute_file(tmp_path / "minutes.csv.zstd", self.two_days())
        out = tmp_path / "daily.csv"
        build_daily_from_minutes(source, out)
        assert out.read_text().splitlines()[0].startswith("date,")

    def test_the_output_reloads_through_the_normal_loader(self, tmp_path):
        source = self.minute_file(tmp_path / "minutes.csv.zstd", self.two_days())
        out = tmp_path / "daily.csv"
        build_daily_from_minutes(source, out)
        assert len(load(out).frame) == 2

    def test_a_day_with_no_close_is_dropped_rather_than_written_as_nan(self, tmp_path):
        # Resampling to daily invents rows for gaps in the minute data. A NaN
        # close is not a price, and `load` rejects the file if one gets through.
        stamps = [
            pd.Timestamp("2024-01-01 08:00", tz="UTC"),
            pd.Timestamp("2024-01-03 08:00", tz="UTC"),
        ]
        rows = {
            "Timestamp": [int(s.timestamp()) for s in stamps],
            "Open": [10.0, 30.0],
            "High": [15.0, 35.0],
            "Low": [9.0, 29.0],
            "Close": [12.0, 32.0],
            "Volume": [1.0, 5.0],
        }
        source = self.minute_file(tmp_path / "minutes.csv.zstd", rows)
        prices = build_daily_from_minutes(source, tmp_path / "daily.csv")
        assert len(prices.frame) == 2, "2 January had no data and must not appear"


class TestPredictWithoutTensorFlow:
    """The scaling and windowing in `predict`, exercised against a stub model.

    TensorFlow is not installed in CI, so the one function that reads the saved
    model had never run there -- including the `leaky` switch, which is the
    whole point of the module. A stub `keras` exercises everything except the
    weights: the MinMax bounds, the window alignment, and the inverse scaling.
    """

    @staticmethod
    def stub_keras(monkeypatch, seen: list):
        """A model that predicts the last value of each window it is given."""

        class Model:
            def predict(self, windows, verbose=0):
                seen.append(np.asarray(windows))
                return np.asarray(windows)[:, -1, :]

        keras = types.ModuleType("keras")
        keras.models = types.SimpleNamespace(load_model=lambda *a, **k: Model())
        monkeypatch.setitem(sys.modules, "keras", keras)

    @staticmethod
    def rising(n: int = 100) -> pd.Series:
        # Strictly increasing, so the series high is in the test portion and
        # only a leaky scaler can have seen it.
        return pd.Series(
            np.arange(100.0, 100.0 + n),
            index=pd.bdate_range("2020-01-01", periods=n),
        )

    def test_a_persistence_model_recovers_the_previous_day_exactly(self, monkeypatch):
        # Scale, window, predict, unscale. If the window alignment is off by one
        # or the inverse scaling does not invert, this is where it shows.
        self.stub_keras(monkeypatch, [])
        close = self.rising()
        out = lstm.predict(close, train_fraction=0.8, lookback=5)
        expected = close.shift(1).reindex(out.index)
        assert np.allclose(out.to_numpy(), expected.to_numpy())

    def test_only_the_held_out_tail_is_predicted(self, monkeypatch):
        self.stub_keras(monkeypatch, [])
        close = self.rising()
        out = lstm.predict(close, train_fraction=0.8, lookback=5)
        # Window i predicts day i + lookback, so every prediction must land at
        # or after the split -- a prediction inside the training period is a
        # result scored on data the model was fitted to.
        assert out.index.min() >= close.index[80]
        assert len(out) == 20

    def test_the_leaky_scaler_is_the_only_one_that_has_seen_the_future_high(
        self, monkeypatch
    ):
        # The difference is observable in what the model is fed: bounds taken
        # from the training portion leave the test portion scaled above 1,
        # because those prices are higher than anything the scaler was shown.
        honest_input: list = []
        self.stub_keras(monkeypatch, honest_input)
        lstm.predict(self.rising(), train_fraction=0.8, leaky=False, lookback=5)
        assert honest_input[0].max() > 1.0

        leaky_input: list = []
        self.stub_keras(monkeypatch, leaky_input)
        lstm.predict(self.rising(), train_fraction=0.8, leaky=True, lookback=5)
        assert leaky_input[0].max() <= 1.0
