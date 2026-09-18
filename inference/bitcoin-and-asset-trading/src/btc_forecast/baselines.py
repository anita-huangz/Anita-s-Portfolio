"""Forecasts to beat.

A model is only as impressive as the baseline it outruns, and price forecasting
has an embarrassing one: **tomorrow will be the same as today.** The random walk
is not a strawman, it is what the efficient-market hypothesis predicts, and a
model that cannot beat it has learned the price level rather than anything about
price changes.

Everything here forecasts one day ahead and is fitted only on data strictly
before the day it predicts. `drift` and `ar` re-fit at every step for that
reason -- fitting once on the whole series and then "predicting" inside it is
the same mistake as scaling before the split.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def naive(close: pd.Series) -> pd.Series:
    """Tomorrow equals today. The random walk.

    Shifted, not copied: `close.shift(1)` at time t is the price at t-1, which
    is the last value actually observable when the forecast is made.
    """
    return close.shift(1)


def drift(close: pd.Series, window: int | None = None) -> pd.Series:
    """Today plus the average log return so far.

    The random walk *with* drift. Bitcoin rose a lot over this sample, so a
    model that only captures the trend should beat the plain naive forecast --
    and if a neural network cannot beat this, it has not learned a trend either.
    """
    log_close = np.log(close)
    returns = log_close.diff()
    mean = (
        returns.expanding(min_periods=2).mean()
        if window is None
        else returns.rolling(window, min_periods=2).mean()
    )
    return np.exp(log_close.shift(1) + mean.shift(1))


def ewma(close: pd.Series, span: int = 10) -> pd.Series:
    """Exponentially weighted average of recent closes.

    Smoother than naive, and worse at a random walk -- included because it is
    the forecast people reach for when a chart looks noisy.
    """
    return close.ewm(span=span, adjust=False).mean().shift(1)


def ar_returns(close: pd.Series, lags: int = 5, min_train: int = 250) -> pd.Series:
    """One-step forecast from an autoregression on log returns, refitted daily.

    The honest linear competitor. If daily returns carry any linear
    autocorrelation, this finds it; if they do not, its coefficients sit near
    zero and it collapses back to the drift forecast -- which is itself the
    finding.

    Refitting every day with only prior data is the expensive part and the
    whole point. `np.linalg.lstsq` on a growing window is cheap enough that
    there is no excuse for fitting once.
    """
    log_close = np.log(close)
    returns = log_close.diff()
    values = returns.to_numpy()
    n = len(values)
    predicted = np.full(n, np.nan)

    for t in range(min_train, n):
        history = values[1 : t]  # strictly before t; index 0 is NaN
        if len(history) <= lags + 1:
            continue
        # Design matrix of `lags` previous returns for each target.
        rows = len(history) - lags
        X = np.column_stack(
            [history[lags - k - 1 : lags - k - 1 + rows] for k in range(lags)]
        )
        X = np.column_stack([np.ones(rows), X])
        y = history[lags:]
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        recent = values[t - lags : t][::-1]
        predicted[t] = beta[0] + beta[1:] @ recent

    forecast_returns = pd.Series(predicted, index=close.index)
    return np.exp(log_close.shift(1) + forecast_returns)


def all_baselines(close: pd.Series, min_train: int = 250) -> pd.DataFrame:
    """Every baseline, aligned on the same index."""
    return pd.DataFrame(
        {
            "naive": naive(close),
            "drift": drift(close),
            "ewma_10": ewma(close, span=10),
            "ar5_returns": ar_returns(close, lags=5, min_train=min_train),
        }
    )
