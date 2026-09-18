"""Drift computation.

Pure functions over a price frame: no network, no printing, no plotting. That
separation is what makes the arithmetic testable, and the arithmetic is the part
that can silently be wrong.
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from itertools import pairwise

import numpy as np
import pandas as pd

from .models import EarningsReport, Stock

logger = logging.getLogger(__name__)

DEFAULT_HORIZONS = (1, 5, 10)

#: Sessions before the announcement, to measure the run-up. A market that has
#: already priced the surprise shows the move here rather than afterwards, and
#: measuring only forward windows cannot tell the two apart.
DEFAULT_PRE_WINDOW = 5


@dataclass(frozen=True)
class DriftRow:
    event_date: date
    baseline_date: date
    surprise_pct: float | None
    returns: dict[int, float]
    #: Return minus the benchmark's return over the identical window. Absent
    #: when no benchmark was supplied.
    abnormal: dict[int, float] = field(default_factory=dict)
    #: Return over the sessions *before* the announcement.
    run_up: float | None = None
    ticker: str | None = None

    def as_record(self) -> dict[str, object]:
        record: dict[str, object] = {
            "event_date": self.event_date,
            "baseline_date": self.baseline_date,
            "surprise_pct": self.surprise_pct,
        }
        if self.ticker is not None:
            record["ticker"] = self.ticker
        if self.run_up is not None:
            record["run_up"] = self.run_up
        record.update({f"{h}d": r for h, r in sorted(self.returns.items())})
        record.update({f"abn_{h}d": r for h, r in sorted(self.abnormal.items())})
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


def _window_return(closes: pd.Series, start: int, offset: int) -> float | None:
    """Return from `start` to `start + offset`, or None if it falls outside."""
    target = start + offset
    if target < 0 or target >= len(closes):
        return None
    base = float(closes.iloc[start])
    if base <= 0:
        return None
    return float(closes.iloc[target]) / base - 1.0


def drift_for_event(
    prices: pd.DataFrame,
    report: EarningsReport,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    benchmark: pd.DataFrame | None = None,
    pre_window: int = DEFAULT_PRE_WINDOW,
    ticker: str | None = None,
) -> DriftRow | None:
    """Returns around one announcement, or None if it cannot be measured.

    When `benchmark` is supplied, each horizon also gets an *abnormal* return:
    the stock's move minus the benchmark's move over the identical calendar
    window. This is the number the drift hypothesis is actually about. A raw
    +4% in a week the whole market rose 4% is not drift, it is beta, and a
    study that reports the raw figure cannot tell them apart.
    """
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

    # Abnormal returns are computed over the benchmark's own sessions, located
    # by the same baseline rule, rather than by position in this stock's index.
    # The two indexes can differ -- a halted day, a different exchange -- and
    # aligning by position rather than date would silently offset the windows.
    abnormal: dict[int, float] = {}
    if benchmark is not None and not benchmark.empty and "Close" in benchmark:
        bench_index = pd.DatetimeIndex(benchmark.index)
        bench_start = _baseline_position(bench_index, report.event_date)
        if bench_start is not None:
            bench_closes = benchmark["Close"]
            for horizon, stock_return in returns.items():
                bench_return = _window_return(bench_closes, bench_start, horizon)
                if bench_return is not None:
                    abnormal[horizon] = stock_return - bench_return

    run_up = _window_return(closes, start, -pre_window) if pre_window else None
    # Measured forwards: the return from `pre_window` sessions before the
    # event up to the event, which is the negative of what the helper gives.
    if run_up is not None:
        prior = start - pre_window
        prior_close = float(closes.iloc[prior])
        run_up = baseline / prior_close - 1.0 if prior_close > 0 else None

    # Nothing measurable at all -- no forward window and no prior window --
    # is the only case worth discarding.
    if not returns and run_up is None:
        return None

    return DriftRow(
        event_date=report.event_date,
        baseline_date=index[start].date(),
        surprise_pct=report.surprise_pct,
        returns=returns,
        abnormal=abnormal,
        run_up=run_up,
        ticker=ticker,
    )


def analyze_drift(
    stock: Stock,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    benchmark: pd.DataFrame | None = None,
    pre_window: int = DEFAULT_PRE_WINDOW,
) -> pd.DataFrame:
    """Drift for every announcement, one row each, sorted by event date."""
    if stock.price_data is None:
        raise ValueError(f"no price data loaded for {stock.ticker}")

    rows = [
        row
        for report in stock.earnings
        if (
            row := drift_for_event(
                stock.price_data, report, horizons, benchmark, pre_window, stock.ticker
            )
        )
        is not None
    ]
    if not rows:
        columns = [
            "event_date", "baseline_date", "surprise_pct", "ticker", "run_up",
            *(f"{h}d" for h in horizons),
        ]
        return pd.DataFrame(columns=columns)

    frame = pd.DataFrame([row.as_record() for row in rows])
    return frame.sort_values("event_date").reset_index(drop=True)


def pool(frames: Iterable[pd.DataFrame]) -> pd.DataFrame:
    """Stack per-stock results into one cross-sectional sample.

    A single company gives at most four announcements a year, which is far too
    few to say anything. Drift is a cross-sectional claim and needs to be
    measured across names.
    """
    usable = [f for f in frames if not f.empty]
    if not usable:
        return pd.DataFrame()
    return (
        pd.concat(usable, ignore_index=True)
        .sort_values("event_date")
        .reset_index(drop=True)
    )


def summarize(
    drift: pd.DataFrame,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
    abnormal: bool = False,
) -> pd.Series:
    """Mean drift per horizon. Does not mutate the input."""
    prefix = "abn_" if abnormal else ""
    columns = [f"{prefix}{h}d" for h in horizons if f"{prefix}{h}d" in drift.columns]
    if drift.empty or not columns:
        return pd.Series(dtype="float64")
    return drift[columns].apply(pd.to_numeric, errors="coerce").mean()


def surprise_correlation(
    drift: pd.DataFrame, horizon: int = 1, abnormal: bool = False
) -> float | None:
    """Correlation between surprise and forward return -- the drift hypothesis.

    None when there are fewer than three usable pairs; a correlation over two
    points is always +/-1 and means nothing.
    """
    column = f"abn_{horizon}d" if abnormal else f"{horizon}d"
    if drift.empty or column not in drift.columns:
        return None
    pairs = drift[["surprise_pct", column]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(pairs) < 3:
        return None
    value = pairs["surprise_pct"].corr(pairs[column])
    return None if pd.isna(value) else float(value)


# --------------------------------------------------------------------------- #
# Cross-sectional tests
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Bucket:
    """One surprise group and the average drift within it."""

    label: str
    n: int
    mean_surprise: float
    mean_return: float
    t_stat: float | None

    @property
    def significant(self) -> bool:
        """Two-sided, roughly 5%. Above ~30 observations the normal
        approximation is close enough that quoting 1.96 is not a pretence."""
        return self.t_stat is not None and abs(self.t_stat) > 1.96


def _t_stat(values: pd.Series) -> float | None:
    """One-sample t against a mean of zero. None below three observations."""
    clean = pd.to_numeric(values, errors="coerce").dropna()
    if len(clean) < 3:
        return None
    sd = float(clean.std(ddof=1))
    if sd == 0:
        return None
    return float(clean.mean() / (sd / np.sqrt(len(clean))))


def surprise_buckets(
    drift: pd.DataFrame,
    horizon: int = 5,
    groups: int = 5,
    abnormal: bool = True,
) -> list[Bucket]:
    """Average drift per surprise group -- the standard way to read PEAD.

    A single correlation collapses the whole relationship to one number and
    hides its shape. Post-earnings drift is the claim that drift rises
    *monotonically* with surprise, so the honest presentation sorts events into
    groups and compares them. If the top group does not beat the bottom, the
    effect is not there, whatever the correlation happens to be.
    """
    column = f"abn_{horizon}d" if abnormal else f"{horizon}d"
    if drift.empty or column not in drift.columns:
        return []

    pairs = drift[["surprise_pct", column]].apply(pd.to_numeric, errors="coerce").dropna()
    # Each group needs enough observations for its mean to mean anything.
    if len(pairs) < groups * 3:
        return []

    try:
        labels = pd.qcut(pairs["surprise_pct"], groups, labels=False, duplicates="drop")
    except ValueError:
        # Too many identical surprise values to cut into distinct groups.
        return []

    out: list[Bucket] = []
    for rank in sorted(pd.Series(labels).dropna().unique()):
        subset = pairs[labels == rank]
        out.append(
            Bucket(
                label=f"Q{int(rank) + 1}",
                n=len(subset),
                mean_surprise=float(subset["surprise_pct"].mean()),
                mean_return=float(subset[column].mean()),
                t_stat=_t_stat(subset[column]),
            )
        )
    return out


@dataclass(frozen=True)
class SpreadTest:
    """The long-short result: top surprise group minus bottom."""

    horizon: int
    spread: float
    t_stat: float | None
    top_n: int
    bottom_n: int
    monotonic: bool

    @property
    def significant(self) -> bool:
        return self.t_stat is not None and abs(self.t_stat) > 1.96


def spread_test(
    drift: pd.DataFrame,
    horizon: int = 5,
    groups: int = 5,
    abnormal: bool = True,
) -> SpreadTest | None:
    """Test the top-minus-bottom surprise group, the tradeable version of PEAD.

    A two-sample Welch t-test, which does not assume the two groups share a
    variance -- they generally do not, since big surprises are noisier.
    """
    buckets = surprise_buckets(drift, horizon, groups, abnormal)
    if len(buckets) < 2:
        return None

    column = f"abn_{horizon}d" if abnormal else f"{horizon}d"
    pairs = drift[["surprise_pct", column]].apply(pd.to_numeric, errors="coerce").dropna()
    labels = pd.qcut(pairs["surprise_pct"], groups, labels=False, duplicates="drop")
    ranks = sorted(pd.Series(labels).dropna().unique())

    top = pairs[labels == ranks[-1]][column]
    bottom = pairs[labels == ranks[0]][column]

    t = None
    if len(top) >= 3 and len(bottom) >= 3:
        vt, vb = float(top.var(ddof=1)), float(bottom.var(ddof=1))
        se = np.sqrt(vt / len(top) + vb / len(bottom))
        if se > 0:
            t = float((top.mean() - bottom.mean()) / se)

    means = [b.mean_return for b in buckets]
    return SpreadTest(
        horizon=horizon,
        spread=float(top.mean() - bottom.mean()),
        t_stat=t,
        top_n=len(top),
        bottom_n=len(bottom),
        monotonic=all(a <= b for a, b in pairwise(means)),
    )


def hit_rate(drift: pd.DataFrame, horizon: int = 5, abnormal: bool = True) -> float | None:
    """Share of events where drift moved in the direction of the surprise.

    A coin flip is 50%. This is the cheapest sanity check on a drift claim,
    and it is unmoved by the handful of huge moves that can carry a mean.
    """
    column = f"abn_{horizon}d" if abnormal else f"{horizon}d"
    if drift.empty or column not in drift.columns:
        return None
    pairs = drift[["surprise_pct", column]].apply(pd.to_numeric, errors="coerce").dropna()
    pairs = pairs[pairs["surprise_pct"] != 0]
    if len(pairs) < 3:
        return None
    agree = (np.sign(pairs["surprise_pct"]) == np.sign(pairs[column])).mean()
    return float(agree)
