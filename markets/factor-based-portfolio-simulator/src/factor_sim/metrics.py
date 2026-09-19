"""Performance statistics over a NAV path."""

from __future__ import annotations

from dataclasses import dataclass

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


# --------------------------------------------------------------------------- #
# Benchmark-relative performance
# --------------------------------------------------------------------------- #


def _aligned_returns(nav: pd.DataFrame, benchmark: pd.Series) -> pd.DataFrame:
    """Daily returns for strategy and benchmark on their shared dates."""
    strategy = nav["NAV"].astype("float64").pct_change()
    bench = benchmark.astype("float64").pct_change()
    frame = pd.concat({"strategy": strategy, "benchmark": bench}, axis=1)
    return frame.dropna()


def benchmark_metrics(nav: pd.DataFrame, benchmark: pd.Series) -> dict[str, float]:
    """How the strategy did *relative to* holding the benchmark.

    A backtest that only reports its own return cannot answer the first
    question anyone asks: was this better than buying the index? Total return
    alone cannot -- a strategy up 300% in a period the market rose 400% lost
    money in the only sense that matters.

    Beta and alpha come from a regression of strategy excess returns on
    benchmark excess returns; tracking error is the volatility of the
    difference, and the information ratio is active return per unit of it.
    """
    aligned = _aligned_returns(nav, benchmark)
    if len(aligned) < 30:
        raise ValueError(
            f"need at least 30 overlapping sessions to regress; got {len(aligned)}"
        )

    s = aligned["strategy"]
    b = aligned["benchmark"]

    variance = float(b.var(ddof=1))
    beta = float(s.cov(b) / variance) if variance > 0 else 0.0
    # Annualised intercept: the return not explained by benchmark exposure.
    alpha = float((s.mean() - beta * b.mean()) * TRADING_DAYS_PER_YEAR)

    active = s - b
    tracking_error = float(active.std(ddof=1) * np.sqrt(TRADING_DAYS_PER_YEAR))
    active_return = float(active.mean() * TRADING_DAYS_PER_YEAR)

    strategy_total = float((1 + s).prod() - 1)
    benchmark_total = float((1 + b).prod() - 1)

    # Up/down capture: share of the benchmark's move captured in each regime.
    # A strategy can beat the index by losing less rather than gaining more,
    # and a single average hides which.
    up, down = b > 0, b < 0
    up_capture = float(s[up].mean() / b[up].mean()) if up.any() and b[up].mean() else 0.0
    down_capture = (
        float(s[down].mean() / b[down].mean()) if down.any() and b[down].mean() else 0.0
    )

    return {
        "beta": beta,
        "alpha": alpha,
        "tracking_error": tracking_error,
        "active_return": active_return,
        "information_ratio": active_return / tracking_error if tracking_error > 0 else 0.0,
        "correlation": float(s.corr(b)),
        "strategy_total_return": strategy_total,
        "benchmark_total_return": benchmark_total,
        "excess_total_return": strategy_total - benchmark_total,
        "up_capture": up_capture,
        "down_capture": down_capture,
        "overlapping_days": float(len(aligned)),
    }


# --------------------------------------------------------------------------- #
# Drawdowns
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Drawdown:
    """One peak-to-trough decline and its recovery."""

    peak_date: pd.Timestamp
    trough_date: pd.Timestamp
    recovery_date: pd.Timestamp | None
    depth: float

    @property
    def drawdown_days(self) -> int:
        return int((self.trough_date - self.peak_date).days)

    @property
    def recovery_days(self) -> int | None:
        if self.recovery_date is None:
            return None
        return int((self.recovery_date - self.trough_date).days)

    @property
    def recovered(self) -> bool:
        return self.recovery_date is not None


def drawdown_periods(nav: pd.DataFrame, top: int = 5) -> list[Drawdown]:
    """The worst declines, with when each began, bottomed, and recovered.

    A single max-drawdown number says how deep the worst loss was and nothing
    about how long it lasted. Two strategies with an identical 30% drawdown are
    not comparable if one recovered in a month and the other took three years,
    and time underwater is what actually decides whether a strategy gets held.
    """
    series = nav["NAV"].astype("float64")
    if len(series) < 2:
        return []

    running_peak = series.cummax()
    underwater = series < running_peak

    periods: list[Drawdown] = []
    start: int | None = None
    for i in range(len(series)):
        if underwater.iloc[i] and start is None:
            # The peak is the session before the decline began.
            start = max(0, i - 1)
        elif not underwater.iloc[i] and start is not None:
            periods.append(_build(series, start, i))
            start = None
    if start is not None:
        # Still underwater at the end of the sample: no recovery date.
        periods.append(_build(series, start, None))

    periods.sort(key=lambda d: d.depth, reverse=True)
    return periods[:top]


def _build(series: pd.Series, start: int, end: int | None) -> Drawdown:
    window = series.iloc[start:end] if end is not None else series.iloc[start:]
    peak_value = float(window.iloc[0])
    trough_pos = int(window.to_numpy().argmin())
    trough_value = float(window.iloc[trough_pos])
    return Drawdown(
        peak_date=window.index[0],
        trough_date=window.index[trough_pos],
        recovery_date=series.index[end] if end is not None else None,
        depth=(peak_value - trough_value) / peak_value if peak_value > 0 else 0.0,
    )


# --------------------------------------------------------------------------- #
# Turnover
# --------------------------------------------------------------------------- #


def turnover(weights: pd.DataFrame) -> dict[str, float]:
    """How much of the book is replaced, and what that costs.

    Transaction costs were charged but never reported, so a strategy could
    look good while its edge was being eaten by trading. Annualised turnover
    is the number to compare against the cost assumption: at 5 bps a side,
    400% annual turnover is a 0.4% drag, which is often larger than the alpha
    being chased.
    """
    if weights.empty or len(weights) < 2:
        return {"average_turnover": 0.0, "annualised_turnover": 0.0, "rebalances": 0.0}

    filled = weights.fillna(0.0)
    # One-way turnover: half the sum of absolute weight changes.
    changes = filled.diff().abs().sum(axis=1).iloc[1:] / 2.0

    span_days = (weights.index[-1] - weights.index[0]).days or 1
    per_year = len(changes) * 365.0 / span_days

    return {
        "average_turnover": float(changes.mean()),
        "annualised_turnover": float(changes.mean() * per_year),
        "rebalances": float(len(weights)),
    }


# --------------------------------------------------------------------------- #
# Rendering
# --------------------------------------------------------------------------- #


def format_benchmark(metrics: dict[str, float], name: str) -> str:
    verdict = (
        "beat" if metrics["excess_total_return"] > 0 else "lost to"
    )
    lines = [
        f"  strategy total     {metrics['strategy_total_return']:+.2%}",
        f"  {name:<18} {metrics['benchmark_total_return']:+.2%}",
        f"  excess             {metrics['excess_total_return']:+.2%}"
        f"  ({verdict} {name} over {int(metrics['overlapping_days'])} sessions)",
        f"  beta               {metrics['beta']:.2f}",
        f"  alpha (annual)     {metrics['alpha']:+.2%}",
        f"  tracking error     {metrics['tracking_error']:.2%}",
        f"  information ratio  {metrics['information_ratio']:.2f}",
        f"  correlation        {metrics['correlation']:.2f}",
        f"  up / down capture  {metrics['up_capture']:.2f} / "
        f"{metrics['down_capture']:.2f}",
    ]
    if metrics["excess_total_return"] > 0 and metrics["beta"] > 1.1:
        lines.append(
            f"  note: it beat {name} while carrying {metrics['beta']:.2f}x its "
            "market exposure, so leverage explains part of the gap."
        )
    return "\n".join(lines)


def format_drawdowns(periods: list[Drawdown]) -> str:
    if not periods:
        return "  no drawdowns (NAV never fell below a prior peak)"
    rows = [f"  {'depth':>7}  {'peak':>10}  {'trough':>10}  {'recovered':>10}  days"]
    for d in periods:
        recovery = d.recovery_date.date().isoformat() if d.recovered else "not yet"
        underwater = (
            str(d.drawdown_days + (d.recovery_days or 0))
            if d.recovered
            else f"{d.drawdown_days}+"
        )
        rows.append(
            f"  {d.depth:>7.2%}  {d.peak_date.date()}  {d.trough_date.date()}  "
            f"{recovery:>10}  {underwater}"
        )
    if any(not d.recovered for d in periods):
        rows.append(
            "  a drawdown marked 'not yet' was still open when the sample "
            "ended, so the final NAV sits below a prior peak"
        )
    return "\n".join(rows)


def format_turnover(stats: dict[str, float], cost_bps: float = 0.0) -> str:
    lines = [
        f"  average turnover   {stats['average_turnover']:.1%} per rebalance",
        f"  annualised         {stats['annualised_turnover']:.1%}",
    ]
    if cost_bps > 0:
        drag = stats["annualised_turnover"] * 2 * cost_bps / 10_000
        lines.append(
            f"  implied cost drag  {drag:.2%}/yr at {cost_bps:.0f} bps a side"
        )
    return "\n".join(lines)
