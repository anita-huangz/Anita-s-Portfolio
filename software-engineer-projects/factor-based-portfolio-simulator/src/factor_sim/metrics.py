"""Performance statistics over a NAV path."""

from __future__ import annotations

import numpy as np
import pandas as pd

from .simulation import TRADING_DAYS_PER_YEAR


def max_drawdown(nav: pd.Series) -> float:
    """Largest peak-to-trough decline, as a positive fraction."""
    if nav.empty:
        return 0.0
    peak = nav.cummax()
    return float(((peak - nav) / peak).max())


def performance_metrics(
    nav: pd.DataFrame, risk_free_rate: float = 0.0
) -> dict[str, float]:
    """Summary statistics.

    Must be given the *full* NAV path. The previous version's `run_simulation`
    returned `nav_df.tail()`, and the caller passed those five rows straight
    into this function, so every published figure described the last week of the
    backtest while claiming to describe three years.
    """
    if nav.empty or "NAV" not in nav.columns:
        raise ValueError("nav must be a non-empty frame with a 'NAV' column")

    series = nav["NAV"].astype("float64")
    if len(series) < 2:
        raise ValueError("need at least two NAV observations to compute returns")

    returns = series.pct_change().dropna()
    total_return = float(series.iloc[-1] / series.iloc[0] - 1.0)

    years = len(series) / TRADING_DAYS_PER_YEAR
    annualized = (1.0 + total_return) ** (1.0 / years) - 1.0 if years > 0 else 0.0

    volatility = float(returns.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    daily_rf = risk_free_rate / TRADING_DAYS_PER_YEAR
    excess = returns - daily_rf
    sharpe = (
        float(excess.mean() / excess.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
        if excess.std(ddof=1) > 0
        else 0.0
    )

    return {
        "total_return": total_return,
        "annualized_return": float(annualized),
        "volatility": volatility,
        "sharpe_ratio": sharpe,
        "max_drawdown": max_drawdown(series),
        "trading_days": float(len(series)),
    }


def format_metrics(metrics: dict[str, float]) -> str:
    return "\n".join(
        [
            f"  total return       {metrics['total_return']:+.2%}",
            f"  annualized return  {metrics['annualized_return']:+.2%}",
            f"  volatility         {metrics['volatility']:.2%}",
            f"  Sharpe ratio       {metrics['sharpe_ratio']:.2f}",
            f"  max drawdown       {metrics['max_drawdown']:.2%}",
            f"  trading days       {int(metrics['trading_days'])}",
        ]
    )
