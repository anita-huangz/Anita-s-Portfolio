"""Presentation. Kept apart from the arithmetic so neither drags in the other."""

from __future__ import annotations

import pandas as pd

from .drift import DEFAULT_HORIZONS, summarize, surprise_correlation


def format_summary(
    drift: pd.DataFrame, horizons: tuple[int, ...] = DEFAULT_HORIZONS
) -> str:
    if drift.empty:
        return "No measurable earnings events."

    lines = [f"{len(drift)} earnings events", "", drift.to_string(index=False), ""]
    means = summarize(drift, horizons)
    lines.append("Average post-earnings drift:")
    for horizon, value in means.items():
        lines.append(f"  {horizon:>4}  {value:+.2%}")

    correlation = surprise_correlation(drift, horizon=horizons[0])
    lines.append("")
    if correlation is None:
        lines.append("Surprise/drift correlation: not enough paired observations.")
    else:
        lines.append(
            f"Surprise vs {horizons[0]}d return correlation: {correlation:+.3f}"
        )
    return "\n".join(lines)


def plot_drift(drift: pd.DataFrame, horizons: tuple[int, ...] = DEFAULT_HORIZONS,
               show: bool = True):
    """Scatter surprise against forward return. Requires the `plot` extra."""
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(figsize=(8, 5))
    for horizon in horizons:
        column = f"{horizon}d"
        if column in drift.columns:
            axes.scatter(drift["surprise_pct"], drift[column], label=f"{horizon}D", alpha=0.75)

    axes.axhline(0, color="gray", linestyle="--", linewidth=1)
    axes.axvline(0, color="gray", linestyle="--", linewidth=1)
    axes.set_xlabel("Earnings surprise (%)")
    axes.set_ylabel("Post-earnings return")
    axes.set_title("Earnings surprise vs post-earnings drift")
    axes.legend()
    axes.grid(True, alpha=0.3)
    figure.tight_layout()

    if show:
        plt.show()
    return figure
