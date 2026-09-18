"""Warming rates, with uncertainty that survives contact with the data.

Fitting a straight line through annual temperatures is the easy part, and the
original scripts did it. The hard part is the error bar, and the textbook one
is wrong here for a specific reason:

**Ordinary least squares assumes independent residuals.** Temperature does not
work that way -- a warm year is followed by a warm year, because oceans and
soil carry heat across the calendar boundary. Positive autocorrelation means
the effective number of independent observations is smaller than the number of
rows, so the OLS standard error is too small, the confidence interval too
narrow, and the p-value too impressed with itself.

Three answers, in increasing order of not caring what the residuals look like:

* **Newey-West**, which corrects the OLS standard error for autocorrelation up
  to a chosen lag.
* **A moving-block bootstrap**, which resamples contiguous blocks of years and
  so reproduces the correlation structure without modelling it.
* **Mann-Kendall with Sen's slope**, which is rank-based and assumes nothing
  about the distribution at all.

Where they agree, the answer is solid. Where they do not, the assumption that
broke is the finding.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy import stats

from .data import Series


@dataclass(frozen=True)
class Trend:
    """A slope in degrees per decade, and how sure we are of it."""

    method: str
    slope: float
    standard_error: float
    p_value: float
    low: float
    high: float

    @property
    def significant(self) -> bool:
        return self.p_value < 0.05

    @property
    def width(self) -> float:
        return self.high - self.low

    def row(self) -> str:
        return (
            f"{self.method:<22}{self.slope:>+8.4f}{self.standard_error:>10.4f}"
            f"   [{self.low:+.4f}, {self.high:+.4f}]{self.p_value:>10.2e}"
        )


def _design(series: Series) -> tuple[np.ndarray, np.ndarray]:
    x = series.decades
    return np.column_stack([np.ones_like(x), x]), series.temperature


def ordinary_least_squares(series: Series) -> Trend:
    """The textbook fit, kept so its error bar can be compared with the others."""
    X, y = _design(series)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    residuals = y - X @ beta
    n, k = X.shape
    sigma2 = float(residuals @ residuals) / (n - k)
    covariance = sigma2 * np.linalg.inv(X.T @ X)
    se = float(np.sqrt(covariance[1, 1]))
    t = beta[1] / se
    p = float(2 * stats.t.sf(abs(t), df=n - k))
    critical = stats.t.ppf(0.975, df=n - k)
    return Trend(
        method="OLS",
        slope=float(beta[1]),
        standard_error=se,
        p_value=p,
        low=float(beta[1] - critical * se),
        high=float(beta[1] + critical * se),
    )


def newey_west(series: Series, lag: int | None = None) -> Trend:
    """OLS slope with a standard error corrected for autocorrelation.

    The lag defaults to the usual `4 (n/100)^(2/9)` rule, which for 75 years
    gives 4. The correction can only widen the interval when residuals are
    positively autocorrelated, which is the normal case for temperature.
    """
    X, y = _design(series)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    residuals = y - X @ beta
    n, k = X.shape
    if lag is None:
        lag = int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))

    # Sandwich estimator: (X'X)^-1 S (X'X)^-1, with S accumulating the
    # autocovariance of the score up to `lag` with Bartlett weights.
    bread = np.linalg.inv(X.T @ X)
    scores = X * residuals[:, None]
    meat = scores.T @ scores
    for h in range(1, lag + 1):
        weight = 1.0 - h / (lag + 1.0)
        cross = scores[h:].T @ scores[:-h]
        meat += weight * (cross + cross.T)
    covariance = bread @ meat @ bread
    se = float(np.sqrt(covariance[1, 1]))

    t = beta[1] / se
    p = float(2 * stats.t.sf(abs(t), df=n - k))
    critical = stats.t.ppf(0.975, df=n - k)
    return Trend(
        method=f"Newey-West (lag {lag})",
        slope=float(beta[1]),
        standard_error=se,
        p_value=p,
        low=float(beta[1] - critical * se),
        high=float(beta[1] + critical * se),
    )


def block_bootstrap(
    series: Series, draws: int = 2000, block: int | None = None, seed: int = 0
) -> Trend:
    """Resample contiguous blocks of *residuals* and refit.

    The residuals, not the temperatures. Resampling the temperatures against a
    fixed time axis scrambles the trend out of the series, so the bootstrap
    distribution centres on zero and the interval comes back as [-0.11, +0.11]
    around a point estimate of +0.235 -- which is what the first version of
    this function did. That is a null distribution, not a sampling
    distribution.

    Blocks rather than individual residuals, because resampling one at a time
    would destroy the autocorrelation and hand back the too-narrow OLS
    interval. Contiguous runs preserve the persistence without needing a model
    of it.
    """
    n = len(series)
    if block is None:
        block = max(2, round(n ** (1 / 3)))
    if block >= n:
        raise ValueError("block must be shorter than the series")

    X, y = _design(series)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    point = float(beta[1])

    fitted = X @ beta
    residuals = y - fitted

    rng = np.random.default_rng(seed)
    starts_available = n - block + 1
    needed = int(np.ceil(n / block))
    slopes = np.empty(draws)
    for i in range(draws):
        starts = rng.integers(0, starts_available, needed)
        index = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        # Fitted trend plus resampled residual structure: the trend stays,
        # only the noise around it is redrawn.
        resampled = fitted + residuals[index]
        fit, *_ = np.linalg.lstsq(X, resampled, rcond=None)
        slopes[i] = fit[1]

    low, high = np.quantile(slopes, [0.025, 0.975])
    se = float(slopes.std(ddof=1))
    # Two-sided p from how much of the bootstrap distribution crosses zero.
    crossing = float(min((slopes <= 0).mean(), (slopes >= 0).mean()))
    return Trend(
        method=f"block bootstrap ({block}y)",
        slope=point,
        standard_error=se,
        p_value=min(1.0, 2 * crossing),
        low=float(low),
        high=float(high),
    )


def mann_kendall(series: Series) -> Trend:
    """Rank-based trend test with Sen's slope as the estimate.

    Assumes nothing about the distribution of the residuals -- only that they
    are exchangeable under the null. The standard test in climatology for
    exactly that reason, and the right cross-check on a least-squares fit.

    Sen's slope is the median of all pairwise slopes, so a single freak year
    moves it barely at all where it would tug a least-squares line.
    """
    x = series.decades
    y = series.temperature
    n = len(y)

    # S statistic: net count of increasing pairs.
    signs = np.sign(y[None, :] - y[:, None])
    s = float(np.sum(np.triu(signs, k=1)))

    # Variance with a tie correction.
    _, counts = np.unique(y, return_counts=True)
    tie_term = float(np.sum(counts * (counts - 1) * (2 * counts + 5)))
    variance = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0

    if s > 0:
        z = (s - 1) / np.sqrt(variance)
    elif s < 0:
        z = (s + 1) / np.sqrt(variance)
    else:
        z = 0.0
    p = float(2 * stats.norm.sf(abs(z)))

    # Sen's slope: median of pairwise slopes, and a distribution-free CI.
    pairs = [
        (y[j] - y[i]) / (x[j] - x[i])
        for i in range(n)
        for j in range(i + 1, n)
        if x[j] != x[i]
    ]
    pairs = np.sort(np.array(pairs))
    slope = float(np.median(pairs))
    critical = stats.norm.ppf(0.975)
    spread = critical * np.sqrt(variance)
    lower_index = int(np.clip((len(pairs) - spread) / 2 - 1, 0, len(pairs) - 1))
    upper_index = int(np.clip((len(pairs) + spread) / 2, 0, len(pairs) - 1))
    return Trend(
        method="Mann-Kendall / Sen",
        slope=slope,
        standard_error=float("nan"),
        p_value=p,
        low=float(pairs[lower_index]),
        high=float(pairs[upper_index]),
    )


@dataclass(frozen=True)
class Autocorrelation:
    """How much each year's residual resembles the one before."""

    lag1: float
    durbin_watson: float
    effective_sample_size: float
    n: int

    @property
    def lag1_p_value(self) -> float:
        """One-sided p for the lag-1 correlation being positive.

        Under the null of no autocorrelation the sample estimate has standard
        error about `1 / sqrt(n)`, which is the standard large-sample result.
        """
        z = self.lag1 * np.sqrt(self.n)
        return float(stats.norm.sf(z))

    @property
    def is_correlated(self) -> bool:
        """Is the lag-1 correlation significantly positive?

        A fixed Durbin-Watson cut-off of 1.5 was the first version of this and
        it is wrong: DW's critical values depend on the sample size and the
        number of regressors, and London's 1.576 sits *below* the 5% bound for
        75 observations while being above the rule of thumb. Testing the
        correlation directly is both n-aware and easier to read.
        """
        return self.lag1_p_value < 0.05

    @property
    def inflation(self) -> float:
        """How much wider the honest standard error should be.

        `sqrt(n / n_eff)`. With lag-1 correlation of 0.5 the effective sample
        is a third of the nominal one, and the OLS error bar is too narrow by
        about 70%.
        """
        return float(np.sqrt(self.n / self.effective_sample_size))


def residual_autocorrelation(series: Series) -> Autocorrelation:
    """Diagnose the assumption that OLS depends on and temperature violates."""
    X, y = _design(series)
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    residuals = y - X @ beta
    n = len(residuals)

    lag1 = float(np.corrcoef(residuals[:-1], residuals[1:])[0, 1])
    diff = np.diff(residuals)
    dw = float((diff @ diff) / (residuals @ residuals))
    # Effective sample size under AR(1), the standard approximation.
    effective = n * (1 - lag1) / (1 + lag1) if lag1 > -1 else float(n)
    return Autocorrelation(
        lag1=lag1,
        durbin_watson=dw,
        effective_sample_size=max(float(effective), 1.0),
        n=n,
    )
