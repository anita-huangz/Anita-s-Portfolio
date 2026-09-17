"""Charts. Separate from the simulation so a backtest never opens a window."""

from __future__ import annotations

import pandas as pd


def plot_nav(nav: pd.DataFrame, title: str = "Factor portfolio NAV", show: bool = True):
    import matplotlib.pyplot as plt

    figure, axes = plt.subplots(figsize=(10, 5))
    axes.plot(nav.index, nav["NAV"], linewidth=1.5)
    axes.set_title(title)
    axes.set_xlabel("Date")
    axes.set_ylabel("NAV ($)")
    axes.grid(True, alpha=0.3)
    figure.tight_layout()
    if show:
        plt.show()
    return figure


def plot_drawdown(nav: pd.DataFrame, show: bool = True):
    import matplotlib.pyplot as plt

    series = nav["NAV"]
    drawdown = (series.cummax() - series) / series.cummax()

    figure, axes = plt.subplots(figsize=(10, 3.5))
    axes.fill_between(drawdown.index, -drawdown, 0, alpha=0.4)
    axes.set_title("Drawdown")
    axes.set_ylabel("Peak-to-trough")
    axes.grid(True, alpha=0.3)
    figure.tight_layout()
    if show:
        plt.show()
    return figure
