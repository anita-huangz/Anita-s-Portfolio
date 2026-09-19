"""The command line and the loaders, exercised without touching the network.

`cli.py` had no tests at all and `sources.py` only its pure parts. Neither
needs a live API to be tested: the payload parser is a pure function, the key
lookup reads the environment, and the CLI takes its two loaders by name so they
can be substituted.
"""

import sys
import types

import matplotlib
import numpy as np
import pandas as pd
import pytest
import requests

# Selected before pyplot is imported: CI has no display, and the default
# backend would fail at import time rather than at plot time.
matplotlib.use("Agg")

import matplotlib.pyplot as plt

from earnings_drift import cli as cli_module
from earnings_drift import sources
from earnings_drift.cli import main
from earnings_drift.models import EarningsReport
from earnings_drift.report import plot_drift
from earnings_drift.sources import (
    MissingAPIKey,
    fmp_api_key,
    load_earnings,
    load_price_data,
    parse_surprises,
)

DATES = pd.bdate_range("2023-01-02", periods=180)


def prices() -> pd.DataFrame:
    rng = np.random.default_rng(0)
    close = 100 * np.cumprod(1 + rng.normal(0.0004, 0.012, len(DATES)))
    return pd.DataFrame({"Close": close}, index=DATES)


def reports() -> list[EarningsReport]:
    return [
        EarningsReport.from_iso("2023-02-01", 1.20, 1.00),
        EarningsReport.from_iso("2023-05-03", 0.80, 1.00),
        EarningsReport.from_iso("2023-08-02", 1.05, 1.00),
    ]


class TestParseSurprises:
    def test_it_reads_a_well_formed_payload(self):
        out = parse_surprises([
            {"date": "2023-02-01", "actualEarningResult": 1.2,
             "estimatedEarning": 1.0},
            {"date": "2022-11-01", "actualEarningResult": 0.9,
             "estimatedEarning": 1.0},
        ])
        assert len(out) == 2
        assert [r.event_date.isoformat() for r in out] == ["2022-11-01", "2023-02-01"], (
            "reports must come back in date order"
        )

    @pytest.mark.parametrize(
        "item",
        [
            {"date": "2023-02-01", "actualEarningResult": None,
             "estimatedEarning": 1.0},
            {"date": "2023-02-01", "actualEarningResult": 1.0,
             "estimatedEarning": None},
            {"date": "", "actualEarningResult": 1.0, "estimatedEarning": 1.0},
            {"actualEarningResult": 1.0, "estimatedEarning": 1.0},
            {"date": "not-a-date", "actualEarningResult": 1.0,
             "estimatedEarning": 1.0},
            {"date": "2023-02-01", "actualEarningResult": "n/a",
             "estimatedEarning": 1.0},
        ],
    )
    def test_an_unusable_row_is_skipped_not_fatal(self, item):
        """One bad row in a payload must not lose the other eleven quarters."""
        assert parse_surprises([item]) == []

    def test_good_rows_survive_alongside_bad_ones(self):
        out = parse_surprises([
            {"date": "2023-02-01", "actualEarningResult": 1.2,
             "estimatedEarning": 1.0},
            {"date": None, "actualEarningResult": None, "estimatedEarning": None},
        ])
        assert len(out) == 1

    def test_an_empty_payload_is_empty(self):
        assert parse_surprises([]) == []


class TestApiKey:
    def test_it_reads_the_environment(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "abc123")
        assert fmp_api_key() == "abc123"

    def test_whitespace_is_stripped(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "  abc123  ")
        assert fmp_api_key() == "abc123"

    def test_a_missing_key_names_the_variable_and_where_to_get_one(self, monkeypatch):
        monkeypatch.delenv("FMP_API_KEY", raising=False)
        with pytest.raises(MissingAPIKey, match="FMP_API_KEY"):
            fmp_api_key()

    def test_an_empty_key_counts_as_missing(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "   ")
        with pytest.raises(MissingAPIKey):
            fmp_api_key()


@pytest.fixture
def offline(monkeypatch):
    """Substitute the two loaders the CLI imported."""
    monkeypatch.setattr(cli_module, "load_price_data", lambda *a, **k: prices())
    monkeypatch.setattr(cli_module, "load_earnings", lambda *a, **k: reports())


class TestCommandLine:
    def test_it_reports_drift(self, offline, capsys):
        assert main(["AAPL", "--start", "2023-01-02", "--end", "2023-09-08"]) == 0
        out = capsys.readouterr().out
        assert "AAPL" in out or "event" in out.lower()
        assert "drift" in out.lower()

    def test_custom_horizons_are_honoured(self, offline, capsys):
        assert main(["AAPL", "--horizons", "1,3"]) == 0
        out = capsys.readouterr().out
        assert "1d" in out and "3d" in out

    def test_verbose_adds_output_rather_than_changing_it(self, offline, capsys):
        main(["AAPL"])
        plain = capsys.readouterr().out
        main(["AAPL", "--verbose"])
        loud = capsys.readouterr().out
        assert len(loud) >= len(plain)

    def test_no_events_is_reported_not_crashed(self, monkeypatch, capsys):
        monkeypatch.setattr(cli_module, "load_price_data", lambda *a, **k: prices())
        monkeypatch.setattr(cli_module, "load_earnings", lambda *a, **k: [])
        code = main(["AAPL"])
        combined = capsys.readouterr()
        assert code in (0, 1)
        assert (combined.out + combined.err).strip()

    def test_a_missing_key_is_reported_not_raised(self, monkeypatch, capsys):
        def explode(*args, **kwargs):
            raise MissingAPIKey("set FMP_API_KEY")

        monkeypatch.setattr(cli_module, "load_price_data", explode)
        # 2, not 1: an unset API key is the caller's configuration, which this
        # repository consistently separates from an operation that failed.
        assert main(["AAPL"]) == 2
        assert "FMP_API_KEY" in capsys.readouterr().err

    def test_a_network_failure_is_reported_not_raised(self, monkeypatch, capsys):
        def explode(*args, **kwargs):
            raise ValueError("connection reset")

        monkeypatch.setattr(cli_module, "load_price_data", explode)
        assert main(["AAPL"]) == 1
        assert "error" in capsys.readouterr().err.lower()

    def test_help_exits_cleanly(self):
        with pytest.raises(SystemExit) as exit:
            main(["--help"])
        assert exit.value.code == 0


class TestPriceLoading:
    """`load_price_data` against a stubbed yfinance, not the live one."""

    @staticmethod
    def with_yfinance(monkeypatch, frame):
        module = types.ModuleType("yfinance")
        module.download = lambda *args, **kwargs: frame  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "yfinance", module)

    def test_a_multiindex_is_flattened_so_close_is_reachable(self, monkeypatch):
        # yfinance returns a column MultiIndex for multi-ticker requests and,
        # unpredictably, for single-ticker ones too. Everything downstream
        # indexes 'Close' by name and breaks on the tuple form.
        raw = pd.DataFrame(
            {("Close", "AAPL"): [1.0, 2.0], ("Open", "AAPL"): [1.0, 2.0]},
            index=DATES[:2],
        )
        raw.columns = pd.MultiIndex.from_tuples(raw.columns)
        self.with_yfinance(monkeypatch, raw)
        frame = load_price_data("AAPL", "2023-01-01", "2023-01-05")
        assert list(frame.columns) == ["Close", "Open"]

    def test_rows_come_back_in_date_order(self, monkeypatch):
        shuffled = pd.DataFrame({"Close": [3.0, 1.0, 2.0]}, index=DATES[[2, 0, 1]])
        self.with_yfinance(monkeypatch, shuffled)
        frame = load_price_data("AAPL", "2023-01-01", "2023-01-05")
        assert frame.index.is_monotonic_increasing
        assert list(frame["Close"]) == [1.0, 2.0, 3.0]

    @pytest.mark.parametrize("empty", [pd.DataFrame(), None])
    def test_no_data_names_the_ticker_and_the_window(self, monkeypatch, empty):
        # A delisted or misspelled ticker returns an empty frame rather than an
        # error, and an empty frame silently becomes zero events downstream.
        self.with_yfinance(monkeypatch, empty)
        with pytest.raises(ValueError, match=r"WRONG.*2023-01-01.*2023-01-05"):
            load_price_data("WRONG", "2023-01-01", "2023-01-05")


class TestEarningsLoading:
    """`load_earnings` against a stubbed `requests.get`."""

    @staticmethod
    def with_response(monkeypatch, payload, status=200):
        captured: dict = {}

        class Response:
            def raise_for_status(self):
                if status >= 400:
                    raise requests.HTTPError(f"{status} error")

            def json(self):
                return payload

        def fake_get(url, params=None, timeout=None):
            captured.update(url=url, params=params, timeout=timeout)
            return Response()

        monkeypatch.setattr(sources.requests, "get", fake_get)
        return captured

    def test_the_key_and_limit_are_sent_and_the_payload_is_parsed(self, monkeypatch):
        monkeypatch.setenv("FMP_API_KEY", "secret")
        captured = self.with_response(
            monkeypatch,
            [{"date": "2023-02-01", "actualEarningResult": 1.2, "estimatedEarning": 1.0}],
        )
        out = load_earnings("AAPL", limit=4, timeout=3.0)
        assert [r.eps_actual for r in out] == [1.2]
        assert captured["params"] == {"limit": 4, "apikey": "secret"}
        assert captured["timeout"] == 3.0
        assert "AAPL" in captured["url"]

    def test_a_missing_key_is_raised_before_the_request_is_made(self, monkeypatch):
        monkeypatch.delenv("FMP_API_KEY", raising=False)

        def refuse(*_args, **_kwargs):
            raise AssertionError("the request went out without a key")

        monkeypatch.setattr(sources.requests, "get", refuse)
        with pytest.raises(MissingAPIKey):
            load_earnings("AAPL")

    def test_an_http_error_propagates_rather_than_becoming_an_empty_result(
        self, monkeypatch
    ):
        monkeypatch.setenv("FMP_API_KEY", "secret")
        self.with_response(monkeypatch, [], status=403)
        with pytest.raises(requests.HTTPError):
            load_earnings("AAPL")

    def test_an_error_object_instead_of_a_list_is_reported_verbatim(self, monkeypatch):
        # FMP answers an over-quota key with a 200 and a JSON object. Treating
        # that as "no earnings" would silently report a drift study over zero
        # events instead of telling the user the key ran out.
        monkeypatch.setenv("FMP_API_KEY", "secret")
        self.with_response(monkeypatch, {"Error Message": "Limit Reach"})
        with pytest.raises(ValueError, match="Limit Reach"):
            load_earnings("AAPL")


class TestPlot:
    """The chart. Rendered to a headless backend and inspected, never shown."""

    @staticmethod
    def frame(adjusted: bool) -> pd.DataFrame:
        prefix = "abn_" if adjusted else ""
        return pd.DataFrame(
            {
                "surprise_pct": [20.0, -20.0, 5.0],
                f"{prefix}1d": [0.02, -0.03, 0.00],
                f"{prefix}5d": [0.04, -0.05, 0.01],
            }
        )

    def test_one_series_per_horizon_present_in_the_frame(self):
        figure = plot_drift(self.frame(adjusted=False), horizons=(1, 5, 21), show=False)
        axes = figure.axes[0]
        # 21d is absent from the frame, so it must not appear as an empty series.
        assert [c.get_label() for c in axes.collections] == ["1D", "5D"]
        plt.close(figure)

    def test_the_axis_label_says_whether_returns_are_abnormal(self):
        raw = plot_drift(self.frame(adjusted=False), horizons=(1, 5), show=False)
        assert raw.axes[0].get_ylabel().startswith("Raw")
        plt.close(raw)

        adjusted = plot_drift(self.frame(adjusted=True), horizons=(1, 5), show=False)
        assert adjusted.axes[0].get_ylabel().startswith("Abnormal")
        plt.close(adjusted)

    def test_the_zero_lines_that_split_the_quadrants_are_drawn(self):
        # The whole point of the scatter is which quadrant a point lands in:
        # positive surprise with a negative drift is the interesting case.
        figure = plot_drift(self.frame(adjusted=False), horizons=(1,), show=False)
        positions = {line.get_ydata()[0] for line in figure.axes[0].lines}
        assert 0 in positions
        plt.close(figure)

    def test_show_is_honoured(self, monkeypatch):
        shown: list[int] = []
        monkeypatch.setattr(plt, "show", lambda *a, **k: shown.append(1))
        plt.close(plot_drift(self.frame(adjusted=False), horizons=(1,), show=True))
        assert shown == [1]
