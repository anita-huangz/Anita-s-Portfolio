"""Drift computation.

Pure functions over a price frame: no network, no printing, no plotting. That
separation is what makes the arithmetic testable, and the arithmetic is the part
that can silently be wrong.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date

import pandas as pd

from .models import EarningsReport, Stock

logger = logging.getLogger(__name__)

DEFAULT_HORIZONS = (1, 5, 10)


@dataclass(frozen=True)
class DriftRow:
    event_date: date
    baseline_date: date
    surprise_pct: float | None
    returns: dict[int, float]

    def as_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "event_date": self.event_date,
            "baseline_date": self.baseline_date,
            "surprise_pct": self.surprise_pct,
        }
        record.update({f"{h}d": r for h, r in sorted(self.returns.items())})
        return record


def _baseline_position(index: pd.DatetimeIndex, event_date: date) -> int | None:
    """Position of the last trading session on or before the event date.

    Earnings are frequently announced after the close, on a holiday, or on a
    weekend. Requiring an exact index match -- as a naive `date in index` check
    does -- silently drops those events, which is a large and non-random slice
    of the sample.
    """
    stamp = pd.Timestamp(event_date)
    positions = index.searchsorted(stamp, side="right") - 1
    position = int(positions)
    return position if position >= 0 else None


def drift_for_event(
    prices: pd.DataFrame,
    report: EarningsReport,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> DriftRow | None:
    """Forward returns after one announcement, or None if it cannot be measured."""
    if prices.empty:
        return None

    index = pd.DatetimeIndex(prices.index)
    start = _baseline_position(index, report.event_date)
    if start is None:
        logger.info("no trading session on or before %s", report.event_date)
        return None

    closes = prices["Close"]
    baseline = float(closes.iloc[start])
    if baseline <= 0:
        logger.warning("non-positive baseline close on %s", index[start].date())
        return None

    returns: dict[int, float] = {}
    for horizon in horizons:
        target = start + horizon
        if target >= len(closes):
            # Not enough history after the event. Omitted rather than filled,
            # so a truncated sample cannot masquerade as a flat return.
            continue
        returns[horizon] = float(closes.iloc[target]) / baseline - 1.0

    if not returns:
        return None

    return DriftRow(
        event_date=report.event_date,
        baseline_date=index[start].date(),
        surprise_pct=report.surprise_pct,
        returns=returns,
    )


def analyze_drift(
    stock: Stock, horizons: tuple[int, ...] = DEFAULT_HORIZONS
) -> pd.DataFrame:
    """Drift for every announcement, one row each, sorted by event date."""
    if stock.price_data is None:
        raise ValueError(f"no price data loaded for {stock.ticker}")

    rows = [
        row
        for report in stock.earnings
        if (row := drift_for_event(stock.price_data, report, horizons)) is not None
    ]
    if not rows:
        columns = ["event_date", "baseline_date", "surprise_pct", *(f"{h}d" for h in horizons)]
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame([row.as_record() for row in rows])
    return frame.sort_values("event_date").reset_index(drop=True)


def summarize(drift: pd.DataFrame, horizons: tuple[int, ...] = DEFAULT_HORIZONS) -> pd.Series:
    """Mean drift per horizon. Does not mutate the input."""
    columns = [f"{h}d" for h in horizons if f"{h}d" in drift.columns]
    if drift.empty or not columns:
        return pd.Series(dtype="float64")
    return drift[columns].apply(pd.to_numeric, errors="coerce").mean()


def surprise_correlation(
    drift: pd.DataFrame, horizon: int = 1
) -> float | None:
    """Correlation between surprise and forward return -- the drift hypothesis.

    None when there are fewer than three usable pairs; a correlation over two
    points is always +/-1 and means nothing.
    """
    column = f"{horizon}d"
    if drift.empty or column not in drift.columns:
        return None
    pairs = drift[["surprise_pct", column]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pairs) < 3:
        return None
    value = pairs["surprise_pct"].corr(pairs[column])
    return None if pd.isna(value) else float(value)
