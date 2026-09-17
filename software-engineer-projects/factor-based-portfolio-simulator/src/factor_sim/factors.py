"""Factor definitions and cross-sectional scoring.

Two things here are easy to get wrong and both change results materially:

1. **Units.** Raw factor values are not comparable. Inverse P/E lands around
   0.03; a 12-month return lands around 0.4. Summing them is arithmetic on
   incomparable scales, and momentum silently dominates. Scores are therefore
   cross-sectionally standardised at each rebalance before being combined.

2. **Direction.** Every factor is defined so that *higher is better*, so the
   combination is a plain sum. Size and volatility are negated at the source.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np
import pandas as pd


class Factor(ABC):
    """A single cross-sectional signal. Higher is always better."""

    #: Column the factor reads from the exposure frame.
    column: str
    name: str

    @abstractmethod
    def raw(self, exposures: pd.Series) -> pd.Series:
        """Per-ticker values for this factor, oriented so higher is better."""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"{type(self).__name__}()"


class ValueFactor(Factor):
    """Cheapness. Inverse P/E, so a lower multiple scores higher."""

    column = "PE"
    name = "value"

    def raw(self, exposures: pd.Series) -> pd.Series:
        pe = pd.to_numeric(exposures, errors="coerce")
        # A non-positive P/E means negative earnings: the multiple carries no
        # cheapness information, so it is excluded rather than ranked as cheap.
        return (1.0 / pe).where(pe > 0)


class MomentumFactor(Factor):
    column = "Momentum12M"
    name = "momentum"

    def raw(self, exposures: pd.Series) -> pd.Series:
        return pd.to_numeric(exposures, errors="coerce")


class SizeFactor(Factor):
    """Small-cap tilt: smaller market cap scores higher."""

    column = "MarketCap"
    name = "size"

    def raw(self, exposures: pd.Series) -> pd.Series:
        caps = pd.to_numeric(exposures, errors="coerce")
        # Log first: raw caps span orders of magnitude, so one mega-cap would
        # otherwise dominate the z-score for every other name.
        return -np.log(caps.where(caps > 0))


class LowVolatilityFactor(Factor):
    column = "Volatility"
    name = "low_volatility"

    def raw(self, exposures: pd.Series) -> pd.Series:
        return -pd.to_numeric(exposures, errors="coerce")


FACTOR_REGISTRY: dict[str, type[Factor]] = {
    "value": ValueFactor,
    "momentum": MomentumFactor,
    "size": SizeFactor,
    "low_volatility": LowVolatilityFactor,
}


def get_factors(names: list[str]) -> list[Factor]:
    unknown = sorted(set(names) - set(FACTOR_REGISTRY))
    if unknown:
        raise ValueError(
            f"unknown factor(s) {unknown}; available: {sorted(FACTOR_REGISTRY)}"
        )
    return [FACTOR_REGISTRY[name]() for name in names]


def zscore(values: pd.Series) -> pd.Series:
    """Cross-sectional z-score, NaN-safe.

    A zero-variance cross-section (every name identical, or a single name)
    yields all zeros rather than NaN or a divide-by-zero, so the factor simply
    contributes nothing to the combined score that period.
    """
    numeric = pd.to_numeric(values, errors="coerce")
    usable = numeric.dropna()
    if usable.empty:
        return pd.Series(0.0, index=values.index, dtype="float64")
    spread = usable.std(ddof=0)
    if not np.isfinite(spread) or spread == 0:
        return pd.Series(0.0, index=values.index, dtype="float64")
    return ((numeric - usable.mean()) / spread).fillna(0.0)


def score_universe(exposures: pd.DataFrame, factors: list[Factor]) -> pd.Series:
    """Combined score per ticker: the sum of each factor's z-score.

    Equal weight across factors. Returns an all-zero series when no requested
    factor has a usable column, which leaves selection to the optimizer's
    deterministic tie-break rather than failing the whole backtest.
    """
    if exposures.empty or not factors:
        return pd.Series(0.0, index=exposures.index, dtype="float64")

    total = pd.Series(0.0, index=exposures.index, dtype="float64")
    for factor in factors:
        if factor.column not in exposures.columns:
            continue
        total = total + zscore(factor.raw(exposures[factor.column]))
    return total
