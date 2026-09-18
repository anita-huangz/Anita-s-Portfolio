"""Metrics that say how uncertain they are, and a test for comparing forecasts.

Three things the original notebook's evaluation could not do.

**Say whether a difference is real.** "RMSE 22,283 against the baseline's
1,401" is a ratio with no standard error on it. The Diebold-Mariano test is the
standard way to ask whether two forecasts differ by more than sampling noise,
and it accounts for the fact that forecast errors on consecutive days are
correlated.

**Say whether 48.6% directional accuracy differs from a coin flip.** On 538
days the standard error is about 2.2 points, so it does not. A number quoted
without that interval invites a conclusion it cannot support.

**Score the thing that matters.** RMSE on a price level is dominated by the
level: it looks catastrophic in a $100k year and excellent in a $400 year for
identically useless forecasts. R-squared on *returns* asks the real question,
and the answer is usually indistinguishable from zero.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats


@dataclass(frozen=True)
class Accuracy:
    """Point accuracy with an interval, so it cannot be over-read."""

    correct: int
    total: int
    #: Days the forecast made no directional call at all.
    abstained: int = 0

    @property
    def rate(self) -> float:
        return self.correct / self.total if self.total else float("nan")

    @property
    def abstention_rate(self) -> float:
        """Share of days the forecast declined to pick a direction.

        The naive forecast abstains on *every* day: predicting "tomorrow
        equals today" implies no direction. Scoring that as 0% correct would
        be wrong -- it is not a wrong call, it is no call -- and scoring it as
        50% would be generous. It is reported separately.
        """
        denominator = self.total + self.abstained
        return self.abstained / denominator if denominator else float("nan")

    def interval(self, alpha: float = 0.05) -> tuple[float, float]:
        """Wilson score interval.

        Wilson rather than the textbook normal approximation because that one
        misbehaves near 0 and 1 and can produce bounds outside [0, 1].
        """
        if self.total == 0:
            return (float("nan"), float("nan"))
        z = stats.norm.ppf(1 - alpha / 2)
        p, n = self.rate, self.total
        centre = (p + z * z / (2 * n)) / (1 + z * z / n)
        half = (
            z
            / (1 + z * z / n)
            * np.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
        )
        return (float(centre - half), float(centre + half))

    @property
    def beats_coin_flip(self) -> bool:
        """Is the interval entirely above 50%?"""
        return self.interval()[0] > 0.5


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual, predicted = _aligned(actual, predicted)
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual, predicted = _aligned(actual, predicted)
    return float(np.mean(np.abs(actual - predicted)))


def mape(actual: np.ndarray, predicted: np.ndarray) -> float:
    actual, predicted = _aligned(actual, predicted)
    return float(np.mean(np.abs((actual - predicted) / actual)) * 100)


def _aligned(actual, predicted) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(actual, dtype=float)
    p = np.asarray(predicted, dtype=float)
    if a.shape != p.shape:
        raise ValueError(f"shapes differ: {a.shape} vs {p.shape}")
    keep = np.isfinite(a) & np.isfinite(p)
    if not keep.any():
        raise ValueError("no overlapping finite values")
    return a[keep], p[keep]


def directional_accuracy(
    actual: pd.Series, predicted: pd.Series, previous: pd.Series
) -> Accuracy:
    """How often the forecast got the *direction* right.

    `previous` is the last observed price, which is what "up or down" is
    measured against.

    Two kinds of day are excluded rather than scored. Days the price did not
    move: there was no direction to get right. And days the *forecast* implies
    no move: that is an abstention, not a wrong call, and it matters because
    the naive forecast abstains on every single day by construction. Counting
    those as errors would report the random walk at 0% directional accuracy,
    which is the sort of number that looks like a finding and is an artefact.
    """
    frame = pd.DataFrame(
        {"actual": actual, "predicted": predicted, "previous": previous}
    ).dropna()
    real = np.sign(frame["actual"] - frame["previous"])
    guess = np.sign(frame["predicted"] - frame["previous"])
    scorable = (real != 0) & (guess != 0)
    return Accuracy(
        correct=int((real[scorable] == guess[scorable]).sum()),
        total=int(scorable.sum()),
        abstained=int(((real != 0) & (guess == 0)).sum()),
    )


def return_r2(actual: pd.Series, predicted: pd.Series, previous: pd.Series) -> float:
    """R-squared of the *implied return* forecast, against predicting zero.

    The number that exposes a level-tracking model. Predicting "no change"
    every day scores exactly 0 here; a negative value means the forecast is
    worse than saying nothing, which a level forecast with a small bias often
    is.
    """
    frame = pd.DataFrame(
        {"actual": actual, "predicted": predicted, "previous": previous}
    ).dropna()
    real = np.log(frame["actual"] / frame["previous"])
    guess = np.log(frame["predicted"] / frame["previous"])
    residual = float(np.sum((real - guess) ** 2))
    total = float(np.sum(real**2))  # against zero, not against the mean
    return 1.0 - residual / total if total > 0 else float("nan")


@dataclass(frozen=True)
class DieboldMariano:
    """Whether two forecasts differ by more than noise."""

    statistic: float
    p_value: float
    mean_loss_difference: float
    observations: int
    lag: int

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    @property
    def better(self) -> str:
        """Which forecast won, or 'neither' when the test cannot tell."""
        if not self.significant:
            return "neither"
        return "first" if self.mean_loss_difference < 0 else "second"


def diebold_mariano(
    actual: np.ndarray,
    first: np.ndarray,
    second: np.ndarray,
    horizon: int = 1,
    power: int = 2,
) -> DieboldMariano:
    """Test that two forecasts have equal expected loss.

    The loss differential `d_t = e1_t^power - e2_t^power` is averaged and
    divided by its long-run standard error. The HAC (Newey-West) correction is
    the reason this is not just a paired t-test: forecast errors on consecutive
    days are correlated, so the naive standard error is too small and every
    comparison looks significant.

    Uses the Harvey-Leybourne-Newbold small-sample correction and a t
    reference distribution, which is the version that behaves on a few hundred
    observations.
    """
    a = np.asarray(actual, dtype=float)
    f1 = np.asarray(first, dtype=float)
    f2 = np.asarray(second, dtype=float)
    keep = np.isfinite(a) & np.isfinite(f1) & np.isfinite(f2)
    a, f1, f2 = a[keep], f1[keep], f2[keep]
    n = a.size
    if n < 10:
        raise ValueError(f"need at least 10 overlapping forecasts; got {n}")

    d = np.abs(a - f1) ** power - np.abs(a - f2) ** power
    d_bar = float(d.mean())

    # Newey-West long-run variance, truncated at the forecast horizon.
    lag = max(horizon - 1, 0)
    centred = d - d_bar
    gamma0 = float(np.mean(centred**2))
    variance = gamma0
    for k in range(1, lag + 1):
        gamma_k = float(np.mean(centred[k:] * centred[:-k]))
        variance += 2 * (1 - k / (lag + 1)) * gamma_k
    variance = max(variance, 1e-300)

    statistic = d_bar / np.sqrt(variance / n)
    # Harvey-Leybourne-Newbold correction for the small-sample bias.
    correction = np.sqrt(
        (n + 1 - horizon + horizon * (horizon - 1) / n) / n
    )
    statistic *= correction
    p_value = float(2 * stats.t.sf(abs(statistic), df=n - 1))

    return DieboldMariano(
        statistic=float(statistic),
        p_value=p_value,
        mean_loss_difference=d_bar,
        observations=int(n),
        lag=lag,
    )
