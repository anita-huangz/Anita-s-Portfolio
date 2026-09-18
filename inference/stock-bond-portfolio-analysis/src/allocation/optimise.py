"""Allocation rules, including the one that keeps winning.

`equal_weight` is here because of a result that will not go away: DeMiguel,
Garlappi and Uppal (2009) tested fourteen mean-variance strategies across
seven datasets and **none reliably beat 1/N out of sample**. The reason is
estimation error -- the optimiser's edge over naive diversification is smaller
than the noise in the inputs it needs.

So 1/N is not a strawman. It is the benchmark, and a strategy that cannot beat
it has not earned the machinery.
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from scipy.optimize import minimize

#: Long-only, fully invested. Short positions would make every result here
#: more extreme and less believable.
BOUNDS = (0.0, 1.0)

Allocator = Callable[[np.ndarray, np.ndarray], np.ndarray]


def _constraints() -> list[dict]:
    return [{"type": "eq", "fun": lambda w: w.sum() - 1.0}]


def equal_weight(expected: np.ndarray, covariance: np.ndarray) -> np.ndarray:
    """1/N. Uses neither input, which is exactly why it is hard to beat."""
    n = len(expected)
    return np.full(n, 1.0 / n)


def minimum_variance(expected: np.ndarray, covariance: np.ndarray) -> np.ndarray:
    """Lowest variance, ignoring expected returns entirely.

    Ignoring them is a feature. Expected returns are the noisiest input, so a
    rule that does not need them inherits far less estimation error -- which is
    why minimum-variance portfolios routinely beat maximum-Sharpe ones out of
    sample despite optimising something nobody wants.
    """
    n = len(expected)
    result = minimize(
        lambda w: w @ covariance @ w,
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=[BOUNDS] * n,
        constraints=_constraints(),
    )
    return _clean(result.x)


def maximum_sharpe(
    expected: np.ndarray, covariance: np.ndarray, risk_free: float = 0.0
) -> np.ndarray:
    """The textbook portfolio, and the one most exposed to estimation error."""
    n = len(expected)

    def negative_sharpe(w: np.ndarray) -> float:
        volatility = np.sqrt(w @ covariance @ w)
        if volatility <= 0:
            return 0.0
        return -float((w @ expected - risk_free) / volatility)

    result = minimize(
        negative_sharpe,
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=[BOUNDS] * n,
        constraints=_constraints(),
    )
    return _clean(result.x)


def risk_parity(expected: np.ndarray, covariance: np.ndarray) -> np.ndarray:
    """Every asset contributes the same share of portfolio variance.

    Also ignores expected returns. Unlike minimum-variance it will not pile
    into the single lowest-volatility asset, which on this universe means it
    does not become a cash fund.
    """
    n = len(expected)

    def dispersion(w: np.ndarray) -> float:
        portfolio_variance = w @ covariance @ w
        if portfolio_variance <= 0:
            return 0.0
        contributions = w * (covariance @ w) / np.sqrt(portfolio_variance)
        return float(np.sum((contributions - contributions.mean()) ** 2))

    result = minimize(
        dispersion,
        np.full(n, 1.0 / n),
        method="SLSQP",
        bounds=[(1e-4, 1.0)] * n,
        constraints=_constraints(),
    )
    return _clean(result.x)


def _clean(weights: np.ndarray) -> np.ndarray:
    """Clip tiny negatives from the solver and renormalise.

    SLSQP returns values like -1e-17 at a boundary. Left alone they make a
    "long-only" portfolio technically short, and the turnover calculation then
    charges for trades that never happened.
    """
    clipped = np.clip(weights, 0.0, None)
    total = clipped.sum()
    return clipped / total if total > 0 else np.full(len(weights), 1.0 / len(weights))


ALLOCATORS: dict[str, Allocator] = {
    "equal weight (1/N)": equal_weight,
    "minimum variance": minimum_variance,
    "maximum Sharpe": maximum_sharpe,
    "risk parity": risk_parity,
}
