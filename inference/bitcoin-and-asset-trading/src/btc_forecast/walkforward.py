"""Rolling-origin evaluation, instead of one arbitrary split.

The notebook took the last 20% of the series as a test set. On a time series
that is one experiment, and bitcoin's last 20% happens to contain the 2024-25
run to $100k -- so the reported score is a statement about that particular
regime, not about the method.

Walk-forward fixes it by running the whole exercise repeatedly: train on
everything up to a point, forecast the next block, move the origin forward,
repeat. The spread across folds is then the honest error bar, and it is usually
much wider than anyone expects.

Two rules, both load-bearing:

**The training window only ever sees the past.** That is what "origin" means.
**Nothing is fitted across folds** -- including scalers. Fitting a MinMax
scaler on the full series before splitting is the same mistake, and
`leakage.py` measures what it is worth here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .metrics import Accuracy, directional_accuracy, return_r2, rmse


@dataclass(frozen=True)
class Fold:
    """One origin: what may be learned from, and what is forecast."""

    index: int
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp
    train_size: int
    test_size: int


def rolling_origin(
    index: pd.DatetimeIndex,
    min_train: int = 1000,
    test_size: int = 180,
    step: int | None = None,
) -> Iterator[Fold]:
    """Expanding-window folds, each forecasting the `test_size` days after it.

    Expanding rather than sliding: a forecaster should be allowed everything
    that has happened, which is the situation it would really be in. `step`
    defaults to `test_size`, giving non-overlapping test blocks -- overlapping
    ones would double-count days and make the fold spread look tighter than it
    is.
    """
    step = step or test_size
    n = len(index)
    if min_train + test_size > n:
        raise ValueError(
            f"need at least {min_train + test_size} observations for one fold; got {n}"
        )
    fold = 0
    start = min_train
    while start + test_size <= n:
        yield Fold(
            index=fold,
            train_end=index[start - 1],
            test_start=index[start],
            test_end=index[start + test_size - 1],
            train_size=start,
            test_size=test_size,
        )
        fold += 1
        start += step


@dataclass(frozen=True)
class FoldResult:
    fold: Fold
    rmse: float
    return_r2: float
    accuracy: Accuracy


@dataclass(frozen=True)
class WalkForwardResult:
    """Per-fold scores and the spread across them."""

    name: str
    folds: list[FoldResult]

    def _values(self, attribute: str) -> np.ndarray:
        return np.array([getattr(f, attribute) for f in self.folds], dtype=float)

    @property
    def mean_rmse(self) -> float:
        return float(np.mean(self._values("rmse")))

    @property
    def rmse_spread(self) -> tuple[float, float]:
        values = self._values("rmse")
        return float(values.min()), float(values.max())

    @property
    def mean_return_r2(self) -> float:
        return float(np.mean(self._values("return_r2")))

    @property
    def folds_beating_zero_r2(self) -> int:
        """How many folds carried any information about returns at all."""
        return int((self._values("return_r2") > 0).sum())

    @property
    def pooled_accuracy(self) -> Accuracy:
        return Accuracy(
            correct=sum(f.accuracy.correct for f in self.folds),
            total=sum(f.accuracy.total for f in self.folds),
            abstained=sum(f.accuracy.abstained for f in self.folds),
        )


def walk_forward(
    close: pd.Series,
    forecaster: Callable[[pd.Series], pd.Series],
    name: str,
    min_train: int = 1000,
    test_size: int = 180,
) -> WalkForwardResult:
    """Evaluate a forecaster over every rolling origin.

    `forecaster` receives a price series and returns one-step-ahead forecasts
    aligned to it. It is called on `close.iloc[:train_end + test_size]` -- the
    training data *plus* the test block -- because a one-step-ahead forecast for
    day t legitimately uses the price on t-1. What it must not do is fit
    anything using days at or after t, which is exactly what the baselines'
    `shift(1)` and expanding windows enforce.
    """
    results = []
    for fold in rolling_origin(
        pd.DatetimeIndex(close.index), min_train=min_train, test_size=test_size
    ):
        visible = close.loc[: fold.test_end]
        forecast = forecaster(visible)
        window = slice(fold.test_start, fold.test_end)
        actual = close.loc[window]
        predicted = forecast.loc[window]
        previous = close.shift(1).loc[window]
        results.append(
            FoldResult(
                fold=fold,
                rmse=rmse(actual, predicted),
                return_r2=return_r2(actual, predicted, previous),
                accuracy=directional_accuracy(actual, predicted, previous),
            )
        )
    return WalkForwardResult(name=name, folds=results)
