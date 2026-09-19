"""Presentation. Kept apart from the arithmetic so neither drags in the other."""

from __future__ import annotations

import pandas as pd

from .drift import (
    DEFAULT_HORIZONS,
    hit_rate,
    spread_test,
    summarize,
    surprise_buckets,
    surprise_correlation,
)

#: Beyond this many events the per-row table stops being readable and the
#: aggregates are what matters.
MAX_ROWS_SHOWN = 24


def format_summary(
    drift: pd.DataFrame, horizons: tuple[int, ...] = DEFAULT_HORIZONS
) -> str:
    if drift.empty:
        return "No measurable earnings events."

    # Market-adjusted where available. Raw drift over a week the whole market
    # moved is mostly beta, and reporting it as drift conflates the two.
    adjusted = any(c.startswith("abn_") for c in drift.columns)
    horizon = _middle(horizons, drift, adjusted)
    basis = "market-adjusted" if adjusted else "raw"

    lines = [f"{len(drift)} earnings events ({basis} returns)", ""]

    shown = [c for c in _display_columns(drift) if c in drift.columns]
    if len(drift) <= MAX_ROWS_SHOWN:
        lines += [drift[shown].to_string(index=False), ""]
    else:
        lines += [
            drift[shown].head(MAX_ROWS_SHOWN // 2).to_string(index=False),
            f"  … {len(drift) - MAX_ROWS_SHOWN} more events …",
            drift[shown].tail(MAX_ROWS_SHOWN // 2).to_string(index=False),
            "",
        ]

    for label, means in (
        ("Average raw drift", summarize(drift, horizons, abnormal=False)),
        ("Average abnormal drift (excess over benchmark)",
         summarize(drift, horizons, abnormal=True) if adjusted else pd.Series(dtype=float)),
    ):
        if not means.empty:
            lines.append(f"{label}:")
            for name, value in means.items():
                lines.append(f"  {name:>9}  {value:+.2%}")
            lines.append("")

    if "run_up" in drift.columns:
        run_up = pd.to_numeric(drift["run_up"], errors="coerce").dropna()
        if not run_up.empty:
            lines += [
                f"Average run-up into the announcement: {run_up.mean():+.2%}",
                "  A market that had already priced the surprise shows the move",
                "  here rather than afterwards.",
                "",
            ]

    correlation = surprise_correlation(drift, horizon=horizon, abnormal=adjusted)
    if correlation is None:
        lines.append("Surprise/drift correlation: not enough paired observations.")
    else:
        lines.append(
            f"Surprise vs {horizon}d {basis} return correlation: {correlation:+.3f}"
        )

    rate = hit_rate(drift, horizon, abnormal=adjusted)
    if rate is not None:
        lines.append(
            f"Drift matched the surprise's sign {rate:.0%} of the time "
            "(a coin flip is 50%)."
        )

    lines += _bucket_lines(drift, horizon, adjusted, basis)
    return "\n".join(lines)


def _middle(horizons: tuple[int, ...], drift: pd.DataFrame, adjusted: bool) -> int:
    """Pick a horizon that exists in the frame, preferring a middle one.

    The shortest horizon is the noisiest, so it is a poor default for the
    headline statistic.
    """
    prefix = "abn_" if adjusted else ""
    available = [h for h in horizons if f"{prefix}{h}d" in drift.columns]
    if not available:
        return horizons[0]
    return available[len(available) // 2]


def _display_columns(drift: pd.DataFrame) -> list[str]:
    base = ["ticker", "event_date", "surprise_pct", "run_up"]
    abnormal = sorted(c for c in drift.columns if c.startswith("abn_"))
    raw = sorted(c for c in drift.columns if c[0].isdigit())
    return base + (abnormal or raw)


def _bucket_lines(
    drift: pd.DataFrame, horizon: int, adjusted: bool, basis: str
) -> list[str]:
    buckets = surprise_buckets(drift, horizon, abnormal=adjusted)
    if not buckets:
        return [
            "",
            "Not enough events to group by surprise. Drift is a cross-sectional",
            "claim, so it needs many announcements -- pool several companies.",
        ]

    lines = [
        "",
        f"Drift by surprise group, {horizon}-day {basis}:",
        f"  {'group':>6} {'n':>4} {'surprise':>10} {'drift':>9} {'t':>7}",
    ]
    for b in buckets:
        t = f"{b.t_stat:+.2f}" if b.t_stat is not None else "n/a"
        lines.append(
            f"  {b.label:>6} {b.n:>4} {b.mean_surprise:>9.1f}% "
            f"{b.mean_return:>+8.2%} {t:>7}{' *' if b.significant else ''}"
        )

    spread = spread_test(drift, horizon, abnormal=adjusted)
    if spread is not None:
        t = f"{spread.t_stat:+.2f}" if spread.t_stat is not None else "n/a"
        lines += ["", f"Top minus bottom group: {spread.spread:+.2%} (t = {t})"]
        if spread.significant:
            lines.append("  Significant at roughly 5%.")
        else:
            lines.append(
                "  Not distinguishable from zero -- on this sample the drift "
                "effect does not hold up."
            )
        if not spread.monotonic:
            lines.append(
                "  Group means are not monotonic in surprise, which is what the "
                "hypothesis predicts they would be."
            )

    lines += ["", "* marks a group mean more than two standard errors from zero."]
    return lines


def plot_drift(drift: pd.DataFrame, horizons: tuple[int, ...] = DEFAULT_HORIZONS,
               show: bool = True):
    """Scatter surprise against forward return. Requires the `plot` extra."""
    import matplotlib.pyplot as plt

    adjusted = any(c.startswith("abn_") for c in drift.columns)
    prefix = "abn_" if adjusted else ""

    figure, axes = plt.subplots(figsize=(8, 5))
    for horizon in horizons:
        column = f"{prefix}{horizon}d"
        if column in drift.columns:
            axes.scatter(drift["surprise_pct"], drift[column], label=f"{horizon}D", alpha=0.75)

    axes.axhline(0, color="gray", linestyle="--", linewidth=1)
    axes.axvline(0, color="gray", linestyle="--", linewidth=1)
    axes.set_xlabel("Earnings surprise (%)")
    axes.set_ylabel(("Abnormal" if adjusted else "Raw") + " post-earnings return")
    axes.set_title("Earnings surprise vs post-earnings drift")
    axes.legend()
    axes.grid(True, alpha=0.3)
    figure.tight_layout()

    if show:
        plt.show()
    return figure
