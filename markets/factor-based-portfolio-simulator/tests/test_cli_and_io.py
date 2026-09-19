"""The three untested modules: the loaders, the plots, and the command line.

Together they were 141 of the project's 488 statements and the whole reason it
sat at 65%, the lowest honest coverage in the repository.

None of them touch the network here. `data.py` imports yfinance, yahooquery and
pandas-datareader *inside* the functions, which is the seam that makes this
possible: the fake goes into `sys.modules` and the real reshaping logic runs on
synthetic frames. That logic is worth testing on its own — the branch between a
MultiIndex and a single-ticker frame is exactly where a loader quietly returns
the wrong shape.
"""

import sys
import types

import matplotlib
import numpy as np
import pandas as pd
import pytest

matplotlib.use("Agg")  # headless: no display in CI


DATES = pd.bdate_range("2023-01-02", periods=60)


def price_frame(tickers: list[str]) -> pd.DataFrame:
    """Deterministic synthetic closes, one column per ticker."""
    rng = np.random.default_rng(0)
    data = {
        t: 100 * np.cumprod(1 + rng.normal(0.0005, 0.01, len(DATES)))
        for t in tickers
    }
    return pd.DataFrame(data, index=DATES)


@pytest.fixture
def fake_yfinance(monkeypatch):
    """A yfinance whose `download` returns a MultiIndex frame, as the real one does."""

    def download(tickers, start=None, end=None, progress=False, auto_adjust=True):
        names = tickers if isinstance(tickers, list) else [tickers]
        closes = price_frame(names)
        columns = pd.MultiIndex.from_product([["Close", "Volume"], names])
        wide = pd.DataFrame(index=DATES, columns=columns, dtype=float)
        for name in names:
            wide[("Close", name)] = closes[name]
            wide[("Volume", name)] = 1000.0
        return wide

    module = types.ModuleType("yfinance")
    module.download = download
    monkeypatch.setitem(sys.modules, "yfinance", module)
    return module


class TestDownloadPrices:
    def test_it_extracts_close_from_a_multiindex(self, fake_yfinance):
        from factor_sim.data import download_prices

        prices = download_prices(["AAA", "BBB"], "2023-01-01", "2023-04-01")
        assert list(prices.columns) == ["AAA", "BBB"]
        assert len(prices) == len(DATES)

    def test_a_single_ticker_still_gives_a_named_column(self, monkeypatch):
        """yfinance collapses to a Series for one ticker; the column must survive."""

        def download(tickers, **kwargs):
            names = tickers if isinstance(tickers, list) else [tickers]
            return pd.DataFrame({"Close": price_frame(names)[names[0]]}, index=DATES)

        module = types.ModuleType("yfinance")
        module.download = download
        monkeypatch.setitem(sys.modules, "yfinance", module)
        from factor_sim.data import download_prices

        prices = download_prices(["AAA"], "2023-01-01", "2023-04-01")
        assert prices.shape[1] == 1

    def test_the_result_is_sorted_by_date(self, monkeypatch):
        def download(tickers, **kwargs):
            frame = price_frame(tickers)
            shuffled = frame.iloc[::-1]  # newest first, as some sources return
            return pd.DataFrame(
                {("Close", t): shuffled[t] for t in tickers},
            ).rename_axis(columns=[None, None])

        module = types.ModuleType("yfinance")
        module.download = download
        monkeypatch.setitem(sys.modules, "yfinance", module)
        from factor_sim.data import download_prices

        prices = download_prices(["AAA", "BBB"], "2023-01-01", "2023-04-01")
        assert prices.index.is_monotonic_increasing

    def test_an_empty_response_is_an_error_not_an_empty_frame(self, monkeypatch):
        """Silently returning nothing would give a backtest of zero days."""
        module = types.ModuleType("yfinance")
        module.download = lambda *a, **k: pd.DataFrame()
        monkeypatch.setitem(sys.modules, "yfinance", module)
        from factor_sim.data import download_prices

        with pytest.raises(ValueError, match="no price data"):
            download_prices(["AAA"], "2023-01-01", "2023-04-01")

    def test_a_none_response_is_also_an_error(self, monkeypatch):
        module = types.ModuleType("yfinance")
        module.download = lambda *a, **k: None
        monkeypatch.setitem(sys.modules, "yfinance", module)
        from factor_sim.data import download_prices

        with pytest.raises(ValueError, match="no price data"):
            download_prices(["AAA"], "2023-01-01", "2023-04-01")


class TestFundamentals:
    def _fake(self, monkeypatch, detail):
        module = types.ModuleType("yahooquery")

        class Ticker:
            def __init__(self, tickers):
                self.tickers = tickers

            @property
            def summary_detail(self):
                return detail

        module.Ticker = Ticker
        monkeypatch.setitem(sys.modules, "yahooquery", module)

    def test_it_returns_one_row_per_ticker(self, monkeypatch):
        self._fake(monkeypatch, {
            "AAA": {"trailingPE": 20.0, "marketCap": 1e9},
            "BBB": {"trailingPE": 10.0, "marketCap": 5e8},
        })
        from factor_sim.data import fetch_fundamentals

        frame = fetch_fundamentals(["AAA", "BBB"])
        assert list(frame.index) == ["AAA", "BBB"]
        assert frame.loc["AAA", "PE"] == 20.0

    def test_a_missing_ticker_becomes_nan_not_an_exception(self, monkeypatch):
        """A delisted name must not take the whole universe down."""
        self._fake(monkeypatch, {"AAA": {"trailingPE": 20.0, "marketCap": 1e9}})
        from factor_sim.data import fetch_fundamentals

        frame = fetch_fundamentals(["AAA", "MISSING"])
        assert np.isnan(frame.loc["MISSING", "PE"])

    def test_a_non_dict_response_is_tolerated(self, monkeypatch):
        """yahooquery returns an error *string* per ticker when it fails."""
        self._fake(monkeypatch, {"AAA": "Quote not found"})
        from factor_sim.data import fetch_fundamentals

        frame = fetch_fundamentals(["AAA"])
        assert np.isnan(frame.loc["AAA", "PE"])


class TestFamaFrench:
    def test_percentages_are_converted_to_decimals(self, monkeypatch):
        """The source publishes percent. Skipping the divide inflates alpha 100x."""
        raw = pd.DataFrame(
            {"Mkt-RF ": [1.0, -2.0], "SMB": [0.5, 0.25], "RF": [0.01, 0.01]},
            index=pd.to_datetime(["2023-01-03", "2023-01-04"]),
        )
        module = types.ModuleType("pandas_datareader.data")
        module.DataReader = lambda *a, **k: {0: raw}
        parent = types.ModuleType("pandas_datareader")
        parent.data = module
        monkeypatch.setitem(sys.modules, "pandas_datareader", parent)
        monkeypatch.setitem(sys.modules, "pandas_datareader.data", module)
        from factor_sim.data import load_fama_french

        frame = load_fama_french()
        assert frame["Mkt-RF"].iloc[0] == pytest.approx(0.01)
        assert "Mkt-RF" in frame.columns, "trailing whitespace must be stripped"
        assert isinstance(frame.index, pd.DatetimeIndex)


class TestPlotting:
    @staticmethod
    def _nav(values):
        # The column really is called NAV; passing anything else raises a
        # KeyError that a "does it draw" test would otherwise not notice.
        return pd.DataFrame(
            {"NAV": values}, index=pd.bdate_range("2023-01-02", periods=len(values))
        )

    def test_plot_nav_draws_without_a_display(self):
        from factor_sim.plotting import plot_nav

        figure = plot_nav(self._nav(np.linspace(100, 130, 40)), show=False)
        assert figure is not None
        assert len(figure.axes) == 1
        assert figure.axes[0].get_ylabel() == "NAV ($)"

    def test_plot_nav_takes_a_title(self):
        from factor_sim.plotting import plot_nav

        figure = plot_nav(self._nav([100.0, 101.0]), title="Custom", show=False)
        assert figure.axes[0].get_title() == "Custom"

    def test_plot_drawdown_draws_without_a_display(self):
        from factor_sim.plotting import plot_drawdown

        figure = plot_drawdown(self._nav([100, 120, 90, 95, 130.0]), show=False)
        assert figure is not None
        assert figure.axes[0].get_title() == "Drawdown"

    def test_the_drawdown_it_plots_is_never_above_zero(self):
        """It fills between -drawdown and 0, so the band must sit at or below 0."""
        from factor_sim.plotting import plot_drawdown

        figure = plot_drawdown(self._nav([100, 120, 90, 95, 130.0]), show=False)
        bottom, top = figure.axes[0].get_ylim()
        assert bottom <= 0
        assert top <= 0.05, "a positive drawdown would mean the sign is flipped"


class TestCommandLine:
    @pytest.fixture(autouse=True)
    def offline(self, monkeypatch, fake_yfinance):
        """Every CLI run here uses synthetic prices and never plots."""
        monkeypatch.setattr(
            "factor_sim.plotting.plot_nav", lambda *a, **k: None, raising=False
        )
        monkeypatch.setattr(
            "factor_sim.plotting.plot_drawdown", lambda *a, **k: None, raising=False
        )

    def test_a_momentum_backtest_runs(self, capsys):
        from factor_sim.cli import main

        assert main([
            "--tickers", "AAA,BBB,CCC", "--start", "2023-01-02", "--end", "2023-03-24",
            "--factors", "momentum", "--top-n", "2", "--rebalance-every", "5",
        ]) == 0
        assert capsys.readouterr().out.strip()

    def test_drawdowns_can_be_requested(self, capsys):
        from factor_sim.cli import main

        assert main([
            "--tickers", "AAA,BBB,CCC", "--start", "2023-01-02", "--end", "2023-03-24",
            "--factors", "momentum", "--top-n", "2", "--rebalance-every", "5",
            "--drawdowns", "3",
        ]) == 0
        assert capsys.readouterr().out.strip()

    def test_an_unknown_flag_exits_nonzero(self):
        from factor_sim.cli import main

        with pytest.raises(SystemExit) as exit:
            main(["--not-a-real-flag"])
        assert exit.value.code != 0

    def test_help_exits_cleanly(self):
        from factor_sim.cli import main

        with pytest.raises(SystemExit) as exit:
            main(["--help"])
        assert exit.value.code == 0
