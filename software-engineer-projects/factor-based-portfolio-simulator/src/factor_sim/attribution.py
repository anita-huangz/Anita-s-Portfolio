"""Fama-French 3-factor attribution of the strategy's excess returns."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

FF_FACTORS = ["Mkt-RF", "SMB", "HML"]


@dataclass
class AttributionResult:
    alpha: float
    alpha_pvalue: float
    betas: dict[str, float]
    pvalues: dict[str, float]
    r_squared: float
    observations: int

    def render(self) -> str:
        lines = [
            f"  observations       {self.observations}",
            f"  alpha (daily)      {self.alpha:+.5f}  (p = {self.alpha_pvalue:.3f})",
        ]
        for name in FF_FACTORS:
            lines.append(
                f"  {name:<18} {self.betas[name]:+.4f}  (p = {self.pvalues[name]:.3f})"
            )
        lines.append(f"  R-squared          {self.r_squared:.3f}")
        return "\n".join(lines)


def align(nav: pd.DataFrame, ff: pd.DataFrame) -> pd.DataFrame:
    """Inner-join NAV returns with the factor frame on normalised dates."""
    left = nav.copy()
    left.index = pd.to_datetime(left.index).normalize()
    right = ff.copy()
    right.index = pd.to_datetime(right.index).normalize()

    merged = left.join(right, how="inner")
    if merged.empty:
        raise ValueError("no overlapping dates between NAV and Fama-French factors")

    merged["Excess_Return"] = merged["Returns"] - merged["RF"]
    return merged.dropna(subset=["Excess_Return", *FF_FACTORS])


def attribute(nav: pd.DataFrame, ff: pd.DataFrame) -> AttributionResult:
    """Regress daily excess return on the three factors.

    Excess_Return = alpha + b1*(Mkt-RF) + b2*SMB + b3*HML + e
    """
    import statsmodels.api as sm

    merged = align(nav, ff)
    if len(merged) <= len(FF_FACTORS) + 1:
        raise ValueError(
            f"need more than {len(FF_FACTORS) + 1} observations to fit; got {len(merged)}"
        )

    exog = sm.add_constant(merged[FF_FACTORS])
    model = sm.OLS(merged["Excess_Return"], exog).fit()

    return AttributionResult(
        alpha=float(model.params["const"]),
        alpha_pvalue=float(model.pvalues["const"]),
        betas={name: float(model.params[name]) for name in FF_FACTORS},
        pvalues={name: float(model.pvalues[name]) for name in FF_FACTORS},
        r_squared=float(model.rsquared),
        observations=int(model.nobs),
    )
