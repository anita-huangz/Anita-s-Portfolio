"""Evaluate the saved LSTM, honestly and as the notebook did.

TensorFlow is an optional dependency: everything else in this package works
without it, and the saved model is a 891 KB artefact rather than something
retrained on every run. `available()` reports whether the comparison can run.

The model is *not* walk-forward evaluated, and that should be said plainly:
retraining a two-layer LSTM at twenty rolling origins is hours of compute for
a result the baselines already settle. If anything that favours the LSTM,
because it is scored on one split while the baselines are scored on all of
them.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .leakage import minmax_scale

MODEL = Path(__file__).resolve().parents[2] / "notebooks" / "bitcoin_lstm_model.h5"
LOOKBACK = 90


def available() -> bool:
    """Is TensorFlow importable and the saved model present?"""
    if not MODEL.exists():
        return False
    try:
        import tensorflow  # noqa: F401
    except ImportError:
        return False
    return True


def sequences(scaled: np.ndarray, lookback: int = LOOKBACK) -> tuple[np.ndarray, np.ndarray]:
    """Sliding windows of `lookback` days, each paired with the next day."""
    windows, targets = [], []
    for i in range(len(scaled) - lookback):
        windows.append(scaled[i : i + lookback])
        targets.append(scaled[i + lookback])
    return np.asarray(windows), np.asarray(targets)


def predict(
    close: pd.Series,
    train_fraction: float = 0.8,
    leaky: bool = False,
    lookback: int = LOOKBACK,
) -> pd.Series:
    """One-step-ahead prices from the saved model, on the held-out tail.

    `leaky=True` reproduces the notebook exactly: the MinMax bounds come from
    the whole series, so the scaler has seen the future high. `leaky=False`
    takes them from the training portion only, which is all that was knowable.
    """
    import keras

    model = keras.models.load_model(MODEL, compile=False)
    values = close.to_numpy(dtype=float)
    split = int(len(values) * train_fraction)

    if leaky:
        low, high = float(values.min()), float(values.max())
    else:
        low, high = float(values[:split].min()), float(values[:split].max())

    scaled = minmax_scale(values, low, high).reshape(-1, 1)
    windows, _ = sequences(scaled, lookback)
    # Window i predicts day i + lookback, so keep the windows whose target
    # falls in the test period.
    keep = np.arange(len(windows)) + lookback >= split
    predicted = model.predict(windows[keep], verbose=0).ravel()
    prices = predicted * (high - low) + low
    return pd.Series(prices, index=close.index[lookback:][keep])
