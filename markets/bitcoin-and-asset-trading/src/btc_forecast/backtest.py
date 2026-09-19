"""Does the forecast make money? The only question that settles it.

Directional accuracy of 51% sounds like an edge and usually is not, because
trading costs are charged on every position change and a coin-flip signal
changes position constantly. A backtest with costs is the test that a
forecast has to pass, and it is much harder than RMSE.

Long/flat rather than long/short: shorting bitcoin has borrow costs and
liquidation risk that a daily-bar backtest cannot model honestly, and
pretending otherwise inflates the result.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

#: Round-trip cost in basis points. 10 bps is a realistic retail taker fee on
#: a major exchange; the point of exposing it is that the answer changes.
DEFAULT_COST_BPS = 10.0

DAYS_PER_YEAR = 365


@dataclass(frozen=True)
class BacktestResult:
    equity: pd.Series
    position: pd.Series
    trades: int
    cost_bps: float

    @property
    def total_return(self) -> float:
        """Growth from the start of the window.

        `equity.iloc[-1] - 1`, not `equity.iloc[-1] / equity.iloc[0] - 1`:
        `(1 + r).cumprod()` already measures growth from 1, so its first entry
        is `1 + r_0` and dividing by it silently throws the first day's return
        away. On a two-day window that is half the result.
        """
        return float(self.equity.iloc[-1] - 1)

    @property
    def annualised_return(self) -> float:
        years = len(self.equity) / DAYS_PER_YEAR
        return float((1 + self.total_return) ** (1 / years) - 1) if years > 0 else 0.0

    @property
    def volatility(self) -> float:
        return float(self.equity.pct_change().std(ddof=1) * np.sqrt(DAYS_PER_YEAR))

    @property
    def sharpe(self) -> float:
        daily = self.equity.pct_change().dropna()
        if daily.std(ddof=1) == 0:
            return 0.0
        return float(daily.mean() / daily.std(ddof=1) * np.sqrt(DAYS_PER_YEAR))

    @property
    def max_drawdown(self) -> float:
        peak = self.equity.cummax()
        return float(((peak - self.equity) / peak).max())

    @property
    def time_in_market(self) -> float:
        return float(self.position.mean())


def backtest_signal(
    close: pd.Series,
    forecast: pd.Series,
    cost_bps: float = DEFAULT_COST_BPS,
) -> BacktestResult:
    """Hold bitcoin on days the forecast says up, hold cash otherwise.

    The position for day t is decided from the forecast *for* day t, which was
    made using data through t-1 -- so the return earned is day t's, and no
    future information enters. Getting this shift wrong is the most common way
    a strategy backtest reports a fortune.
    """
    # `previous` comes from the *full* price series, not from the filtered
    # frame. Taking it after dropping rows with no forecast would discard the
    # first forecastable day as well -- its own previous close having gone out
    # with the NaN row -- which silently shortens every backtest window by a
    # day and, on a short window, by a meaningful share of it.
    previous_all = close.shift(1)
    frame = pd.DataFrame(
        {"close": close, "forecast": forecast, "previous": previous_all}
    ).dropna()
    previous = frame["previous"]

    # Long when the forecast is above the last observed price.
    position = (frame["forecast"] > previous).astype(float)
    market_return = frame["close"] / previous - 1

    turnover = position.diff().abs().fillna(position.iloc[0])
    cost = turnover * cost_bps / 10_000
    strategy_return = position * market_return - cost

    return BacktestResult(
        equity=(1 + strategy_return).cumprod(),
        position=position,
        trades=int(turnover.sum()),
        cost_bps=cost_bps,
    )


def buy_and_hold(close: pd.Series) -> BacktestResult:
    """The benchmark any bitcoin strategy has to beat, and rarely does."""
    frame = close.dropna()
    returns = frame.pct_change().dropna()
    return BacktestResult(
        equity=(1 + returns).cumprod(),
        position=pd.Series(1.0, index=returns.index),
        trades=1,
        cost_bps=0.0,
    )
