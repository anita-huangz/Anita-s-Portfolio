"""Rolling out-of-sample evaluation, which is the only kind that counts.

The original notebook estimated factor loadings and expected returns on a
training period, optimised, and reported the resulting portfolio's statistics.
Those statistics describe a portfolio chosen *with knowledge of* the returns it
is then scored on -- the in-sample result, and always the flattering one.

Here the estimation window only ever precedes the holding period: estimate on
the trailing window, hold those weights for the next block, rebalance, repeat.
Nothing is fitted using a day it is later scored on.

Transaction costs are charged on rebalancing because they are what separates
the strategies. An optimiser that rewrites the book every quarter can look good
gross and lose to 1/N net, and that comparison is the point.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from .data import TRADING_DAYS
from .estimate import expected_returns, ledoit_wolf, sample_covariance
from .optimise import Allocator

#: One-way cost per unit turnover. 5 bps is realistic for liquid ETFs.
DEFAULT_COST_BPS = 5.0


@dataclass(frozen=True)
class BacktestResult:
    name: str
    equity: pd.Series
    weights: pd.DataFrame
    cost_bps: float
    gross_equity: pd.Series = field(default_factory=pd.Series)

    @property
    def total_return(self) -> float:
        return float(self.equity.iloc[-1] - 1)

    @property
    def annualised_return(self) -> float:
        years = len(self.equity) / TRADING_DAYS
        return float(self.equity.iloc[-1] ** (1 / years) - 1) if years > 0 else 0.0

    @property
    def volatility(self) -> float:
        return float(self.equity.pct_change().std(ddof=1) * np.sqrt(TRADING_DAYS))

    @property
    def sharpe(self) -> float:
        daily = self.equity.pct_change().dropna()
        sd = daily.std(ddof=1)
        return float(daily.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0

    @property
    def max_drawdown(self) -> float:
        peak = self.equity.cummax()
        return float(((peak - self.equity) / peak).max())

    #: One-way turnover actually traded at each rebalance.
    turnovers: list[float] = field(default_factory=list)

    @property
    def average_turnover(self) -> float:
        """One-way turnover per rebalance, as actually traded.

        Recorded during the backtest rather than derived from consecutive
        target weights. Those differ: between rebalances the book drifts with
        prices, so returning to a *fixed* target still requires trading. An
        earlier version compared target to target and reported 1/N as having
        zero turnover, when quarterly rebalancing back to equal weight trades
        every quarter.
        """
        return float(np.mean(self.turnovers)) if self.turnovers else 0.0

    @property
    def cost_drag(self) -> float:
        """Annualised return given up to trading."""
        if self.gross_equity.empty:
            return float("nan")
        years = len(self.equity) / TRADING_DAYS
        gross = self.gross_equity.iloc[-1] ** (1 / years) - 1
        return float(gross - self.annualised_return)

    def row(self) -> str:
        return (
            f"{self.name:<22}{self.annualised_return:>+9.2%}{self.volatility:>9.2%}"
            f"{self.sharpe:>8.2f}{self.max_drawdown:>10.1%}"
            f"{self.average_turnover:>11.1%}{self.cost_drag:>9.2%}"
        )


def rolling_backtest(
    returns: pd.DataFrame,
    allocator: Allocator,
    name: str,
    lookback: int = 504,
    rebalance_every: int = 63,
    cost_bps: float = DEFAULT_COST_BPS,
    shrink: bool = True,
) -> BacktestResult:
    """Estimate on the trailing window, hold, rebalance, repeat.

    `lookback` of 504 days is two years and `rebalance_every` of 63 is roughly
    quarterly. Both are arguments because both change the answer, and a result
    that only holds at one setting is not a result.
    """
    if lookback < 30:
        raise ValueError("lookback is too short to estimate a covariance matrix")
    if len(returns) <= lookback:
        raise ValueError(
            f"need more than {lookback} rows to have anything out of sample"
        )

    dates = returns.index
    values = returns.to_numpy(dtype=float)
    n_assets = values.shape[1]

    weights = np.full(n_assets, 1.0 / n_assets)
    held: list[pd.Series] = []
    turnovers: list[float] = []
    net_returns, gross_returns, index = [], [], []

    for t in range(lookback, len(values)):
        if (t - lookback) % rebalance_every == 0:
            window = returns.iloc[t - lookback : t]
            covariance = (
                ledoit_wolf(window)[0] if shrink else sample_covariance(window)
            )
            target = allocator(expected_returns(window), covariance)
            turnover = float(np.abs(target - weights).sum() / 2)
            cost = turnover * cost_bps / 10_000
            turnovers.append(turnover)
            weights = target
            held.append(pd.Series(target, index=returns.columns, name=dates[t]))
        else:
            cost = 0.0

        gross = float(weights @ values[t])
        net_returns.append(gross - cost)
        gross_returns.append(gross)
        index.append(dates[t])
        # Drift: weights move with prices between rebalances.
        grown = weights * (1 + values[t])
        weights = grown / grown.sum()

    return BacktestResult(
        name=name,
        equity=(1 + pd.Series(net_returns, index=index)).cumprod(),
        gross_equity=(1 + pd.Series(gross_returns, index=index)).cumprod(),
        weights=pd.DataFrame(held),
        cost_bps=cost_bps,
        turnovers=turnovers,
    )


def in_sample_result(
    returns: pd.DataFrame, allocator: Allocator, name: str, shrink: bool = True
) -> BacktestResult:
    """Optimise on the whole history, then score on the same history.

    What the original notebook reported. Kept so the gap between it and the
    out-of-sample number can be measured rather than described.
    """
    covariance = ledoit_wolf(returns)[0] if shrink else sample_covariance(returns)
    weights = allocator(expected_returns(returns), covariance)
    portfolio = returns.to_numpy(dtype=float) @ weights
    return BacktestResult(
        name=name,
        equity=(1 + pd.Series(portfolio, index=returns.index)).cumprod(),
        gross_equity=(1 + pd.Series(portfolio, index=returns.index)).cumprod(),
        weights=pd.DataFrame([pd.Series(weights, index=returns.columns)]),
        cost_bps=0.0,
    )


def weight_instability(result: BacktestResult) -> float:
    """Average absolute change in each weight between rebalances.

    The direct measure of estimation error reaching the portfolio. A rule
    whose weights swing violently from one quarter to the next is responding
    to noise, because the underlying assets did not change that much.
    """
    if len(result.weights) < 2:
        return 0.0
    return float(result.weights.diff().abs().mean().mean())
