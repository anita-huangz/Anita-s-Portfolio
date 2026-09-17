"""Quantify the look-ahead bias that the original simulator contained.

The first version computed every factor once from the whole sample
(`price_data.pct_change(252).iloc[-1]`) and reused that snapshot at every
rebalance. The 2021 allocation was therefore chosen using 2024 returns.

This reproduces both the buggy and the corrected loop over identical synthetic
price paths, so the difference is attributable only to when the factors were
measured.

    python examples/lookahead_demo.py
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from factor_sim import get_factors, performance_metrics, run_backtest
from factor_sim.factors import score_universe
from factor_sim.optimizer import RankBasedOptimizer
from factor_sim.portfolio import Portfolio
from factor_sim.simulation import point_in_time_exposures

SEED = 42
N_NAMES = 8
N_DAYS = 750
REBALANCE_EVERY = 21
TOP_N = 2


def synthetic_prices() -> pd.DataFrame:
    """Random walks with a mid-sample regime change, so leadership rotates."""
    rng = np.random.default_rng(SEED)
    index = pd.bdate_range("2021-01-04", periods=N_DAYS)
    columns = {}
    for i in range(N_NAMES):
        drift = rng.normal(0.0002, 0.0004)
        shocks = rng.normal(drift, 0.015, N_DAYS)
        shocks[N_DAYS // 2 :] += rng.normal(0, 0.0006)
        columns[f"S{i}"] = 100 * np.cumprod(1 + shocks)
    return pd.DataFrame(columns, index=index)


def run_with_full_sample_factors(prices: pd.DataFrame, factors: list) -> pd.DataFrame:
    """The original behaviour: score once using the end of the sample."""
    scores = score_universe(point_in_time_exposures(prices, prices.index[-1]), factors)
    optimizer = RankBasedOptimizer(top_n=TOP_N)
    portfolio = Portfolio(cash=100_000.0)

    rows = []
    for i, day in enumerate(prices.index):
        available = {t: float(p) for t, p in prices.loc[day].items() if p > 0}
        if i % REBALANCE_EVERY == 0:
            portfolio.rebalance(optimizer.optimize(scores), available)
        rows.append((day, portfolio.value(available)))
    return pd.DataFrame(rows, columns=["Date", "NAV"]).set_index("Date")


def main() -> None:
    prices = synthetic_prices()
    factors = get_factors(["momentum"])

    correct = performance_metrics(
        run_backtest(prices, factors, top_n=TOP_N, rebalance_every=REBALANCE_EVERY).nav
    )
    buggy = performance_metrics(run_with_full_sample_factors(prices, factors))

    print(f"{'':<24}{'point-in-time':>16}{'full-sample (bug)':>20}")
    for key in ("total_return", "annualized_return", "max_drawdown"):
        print(f"  {key:<22}{correct[key]:>15.2%}{buggy[key]:>20.2%}")
    print(f"  {'sharpe_ratio':<22}{correct['sharpe_ratio']:>15.2f}"
          f"{buggy['sharpe_ratio']:>20.2f}")
    print(
        f"\n  total return overstated by "
        f"{buggy['total_return'] - correct['total_return']:+.1%}"
    )


if __name__ == "__main__":
    main()
