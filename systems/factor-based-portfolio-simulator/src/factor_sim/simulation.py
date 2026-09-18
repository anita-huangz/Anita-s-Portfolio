"""The backtest loop.

The central correctness property here is **point-in-time exposure**: at each
rebalance, factors are computed from prices *up to and including that date and
no further*. The previous version computed every factor once from the full
sample (`price_data.pct_change(252).iloc[-1]`) and reused that single snapshot
at every rebalance, so the 2022 allocation was chosen using 2024 returns. That
is look-ahead bias, and it inflates backtested performance arbitrarily.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .factors import Factor, score_universe
from .optimizer import RankBasedOptimizer
from .portfolio import Portfolio

TRADING_DAYS_PER_YEAR = 252
MOMENTUM_LOOKBACK = 252
VOLATILITY_WINDOW = 21


@dataclass
class BacktestResult:
    """Full history. Note the `nav` frame is complete, not truncated."""

    nav: pd.DataFrame
    weights: pd.DataFrame
    total_costs: float = 0.0
    rebalance_dates: list[pd.Timestamp] = field(default_factory=list)
    skipped_rebalances: int = 0

    @property
    def final_nav(self) -> float:
        return float(self.nav["NAV"].iloc[-1])


def point_in_time_exposures(
    prices: pd.DataFrame,
    as_of: pd.Timestamp,
    static: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Factor exposures using only data available on `as_of`.

    `static` carries fundamentals (P/E, market cap) that are only obtainable as
    a current snapshot from free sources. Reusing today's snapshot at a past
    rebalance is itself look-ahead; the caller is warned about this, and a
    price-only run avoids it entirely.
    """
    history = prices.loc[:as_of]
    exposures = pd.DataFrame(index=prices.columns)

    if len(history) > MOMENTUM_LOOKBACK:
        past = history.iloc[-(MOMENTUM_LOOKBACK + 1)]
        exposures["Momentum12M"] = (history.iloc[-1] / past) - 1.0
    else:
        # Not enough history yet: leave it undefined rather than computing a
        # short-window return and labelling it 12-month momentum.
        exposures["Momentum12M"] = np.nan

    if len(history) > VOLATILITY_WINDOW:
        daily = history.pct_change().iloc[-VOLATILITY_WINDOW:]
        exposures["Volatility"] = daily.std(ddof=0) * np.sqrt(TRADING_DAYS_PER_YEAR)
    else:
        exposures["Volatility"] = np.nan

    if static is not None:
        for column in static.columns:
            exposures[column] = static[column].reindex(exposures.index)

    return exposures


def run_backtest(
    prices: pd.DataFrame,
    factors: list[Factor],
    initial_cash: float = 100_000.0,
    rebalance_every: int = 21,
    top_n: int = 3,
    scheme: str = "equal",
    cost_bps: float = 0.0,
    static_exposures: pd.DataFrame | None = None,
) -> BacktestResult:
    """Run the strategy and return the complete NAV path.

    `prices` is a DataFrame of daily closes, one column per ticker.
    """
    if prices.empty:
        raise ValueError("price data is empty")
    if rebalance_every < 1:
        raise ValueError("rebalance_every must be at least 1")

    prices = prices.sort_index()
    portfolio = Portfolio(cash=initial_cash, cost_bps=cost_bps)
    optimizer = RankBasedOptimizer(top_n=top_n, scheme=scheme)

    nav_rows: list[tuple[pd.Timestamp, float]] = []
    weight_rows: dict[pd.Timestamp, dict[str, float]] = {}
    rebalance_dates: list[pd.Timestamp] = []
    total_costs = 0.0
    skipped = 0

    for i, day in enumerate(prices.index):
        row = prices.loc[day]
        available = {
            ticker: float(price)
            for ticker, price in row.items()
            if pd.notna(price) and float(price) > 0
        }

        if i % rebalance_every == 0 and available:
            exposures = point_in_time_exposures(prices, day, static_exposures)
            exposures = exposures.loc[[t for t in exposures.index if t in available]]
            scores = score_universe(exposures, factors)
            weights = optimizer.optimize(scores)
            if weights:
                total_costs += portfolio.rebalance(weights, available)
                weight_rows[day] = weights
                rebalance_dates.append(day)
            else:
                skipped += 1

        nav_rows.append((day, portfolio.value(available)))

    nav = pd.DataFrame(nav_rows, columns=["Date", "NAV"]).set_index("Date")
    nav["Returns"] = nav["NAV"].pct_change()

    weights_frame = (
        pd.DataFrame.from_dict(weight_rows, orient="index").fillna(0.0)
        if weight_rows
        else pd.DataFrame()
    )

    return BacktestResult(
        nav=nav,
        weights=weights_frame,
        total_costs=total_costs,
        rebalance_dates=rebalance_dates,
        skipped_rebalances=skipped,
    )
