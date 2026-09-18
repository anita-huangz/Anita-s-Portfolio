"""What fitting the scaler on the whole series was worth.

The notebook's sequence was:

```python
scaler = MinMaxScaler()
scaled = scaler.fit_transform(daily_close)      # the WHOLE series
X, y = create_sequences(scaled, 90)
X_train, X_test = X[:split], X[split:]          # split AFTER scaling
```

On a price series that is not a small slip. `MinMaxScaler` divides by
`max - min`, and bitcoin's maximum occurs in the *test* period -- so the
training data was normalised using the all-time high before it happened. The
model is told, in the units it learns in, exactly how high the price will
eventually go.

This module measures it: the same scaling, honest and leaky, with everything
else held fixed. Reported rather than asserted, because "leakage inflates
results" is a claim and a number is evidence.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class ScalerLeak:
    """How much of the test range the training scaler should not have seen."""

    train_max: float
    train_min: float
    full_max: float
    full_min: float
    split_date: pd.Timestamp

    @property
    def range_inflation(self) -> float:
        """Full range divided by the range actually knowable at training time."""
        honest = self.train_max - self.train_min
        leaky = self.full_max - self.full_min
        return leaky / honest if honest > 0 else float("inf")

    @property
    def unseen_high_fraction(self) -> float:
        """Share of the leaky scale that lies above anything ever seen in training.

        This is the part the model could not have known. At 0.46, nearly half
        of the scaled axis is territory the training data never reached.
        """
        leaky = self.full_max - self.full_min
        if leaky <= 0:
            return 0.0
        return max(0.0, (self.full_max - self.train_max) / leaky)


def measure_scaler_leak(close: pd.Series, train_fraction: float = 0.8) -> ScalerLeak:
    """Compare what the scaler saw with what it was entitled to see."""
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    split = int(len(close) * train_fraction)
    if split < 2 or split >= len(close):
        raise ValueError("series too short to split")
    train = close.iloc[:split]
    return ScalerLeak(
        train_max=float(train.max()),
        train_min=float(train.min()),
        full_max=float(close.max()),
        full_min=float(close.min()),
        split_date=pd.Timestamp(close.index[split]),
    )


def minmax_scale(values: np.ndarray, low: float, high: float) -> np.ndarray:
    """Scale to [0, 1] using bounds supplied by the caller.

    Taking the bounds as arguments is the point: it makes "which rows did the
    scaler see" an explicit decision rather than a side effect of statement
    order.
    """
    span = high - low
    if span <= 0:
        raise ValueError("high must exceed low")
    return (np.asarray(values, dtype=float) - low) / span


@dataclass(frozen=True)
class LeakComparison:
    """The same forecast scored under honest and leaky scaling."""

    honest_rmse: float
    leaky_rmse: float

    @property
    def inflation(self) -> float:
        """How many times better the leaky version looks."""
        return self.honest_rmse / self.leaky_rmse if self.leaky_rmse > 0 else float("inf")
