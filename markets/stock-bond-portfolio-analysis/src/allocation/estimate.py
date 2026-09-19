"""Estimating the inputs, which is where mean-variance optimisation goes wrong.

Markowitz needs expected returns and a covariance matrix. Both are estimated
from a finite sample, and the optimiser treats them as if they were known --
so it aggressively exploits whatever estimation error happens to be there.
The result is famously unstable: small changes in the inputs produce large
changes in the weights, and the weights that look best in-sample are the ones
fitted hardest to noise.

Two standard defences live here. **Shrinkage** pulls the covariance matrix
toward a simple structured target, trading a little bias for a lot of variance.
And **the expected-return problem is mostly unfixable**, which is why
minimum-variance and risk-parity portfolios -- which do not use expected
returns at all -- so often beat maximum-Sharpe ones out of sample.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .data import TRADING_DAYS


def sample_covariance(returns: pd.DataFrame) -> np.ndarray:
    """The textbook estimate, annualised."""
    return returns.cov().to_numpy() * TRADING_DAYS


def ledoit_wolf(returns: pd.DataFrame) -> tuple[np.ndarray, float]:
    """Shrink the sample covariance toward a constant-correlation target.

    Returns the shrunk matrix and the intensity used. The intensity is chosen
    to minimise expected squared error, following Ledoit and Wolf, and is
    reported rather than hidden: a shrinkage of 0.8 means the sample matrix was
    mostly discarded, which is worth knowing before trusting weights derived
    from it.

    Implemented here rather than imported so the intensity can be inspected;
    `tests` checks it against scikit-learn's.
    """
    X = returns.to_numpy(dtype=float)
    n, p = X.shape
    if n < 2:
        raise ValueError("need at least two observations")

    centred = X - X.mean(axis=0)
    # n - 1, matching `sample_covariance` and pandas' `.cov()`. The classical
    # Ledoit-Wolf derivation divides by n; mixing the two conventions makes
    # the shrunk matrix's diagonal disagree with the sample variance by a
    # factor of n/(n-1), which is small, silent, and wrong.
    sample = centred.T @ centred / (n - 1)

    # Constant-correlation target: keep each variance, replace every
    # correlation with the average one.
    variances = np.diag(sample)
    std = np.sqrt(variances)
    outer = np.outer(std, std)
    correlations = sample / outer
    off_diagonal = correlations[~np.eye(p, dtype=bool)]
    mean_correlation = off_diagonal.mean()
    target = mean_correlation * outer
    np.fill_diagonal(target, variances)

    # Ledoit-Wolf intensity: dispersion of the sample estimator against how
    # far the target sits from it.
    squared = centred**2
    phi = float(((squared.T @ squared) / n - sample**2).sum())
    gamma = float(((target - sample) ** 2).sum())
    intensity = 0.0 if gamma <= 0 else max(0.0, min(1.0, phi / n / gamma))

    shrunk = intensity * target + (1 - intensity) * sample
    return shrunk * TRADING_DAYS, intensity


def expected_returns(returns: pd.DataFrame) -> np.ndarray:
    """Annualised sample mean.

    Kept deliberately naive, because the honest position is that expected
    returns cannot be estimated well from a decade of data: the standard error
    on a mean return is roughly the volatility divided by the square root of
    the years, which for equities is several percentage points on a number
    that is itself several percentage points. Dressing that up with a factor
    model does not fix it, and the backtest shows what relying on it costs.
    """
    return returns.mean().to_numpy() * TRADING_DAYS
