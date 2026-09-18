"""Domain types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

import pandas as pd


@dataclass(frozen=True)
class EarningsReport:
    """One quarterly announcement and the consensus it was measured against."""

    event_date: date
    eps_actual: float
    eps_estimate: float

    @classmethod
    def from_iso(cls, day: str, eps_actual: float, eps_estimate: float) -> EarningsReport:
        return cls(
            event_date=datetime.strptime(day, "%Y-%m-%d").date(),
            eps_actual=float(eps_actual),
            eps_estimate=float(eps_estimate),
        )

    @property
    def surprise(self) -> float:
        """Raw EPS beat or miss."""
        return self.eps_actual - self.eps_estimate

    @property
    def surprise_pct(self) -> float | None:
        """Surprise as a percentage of the absolute estimate.

        Returns None when the estimate is zero. A zero estimate makes the
        percentage undefined, not zero -- reporting 0.0 would put a genuine
        surprise on the x-axis at "no surprise" and quietly bias the result.
        """
        if self.eps_estimate == 0:
            return None
        return (self.surprise / abs(self.eps_estimate)) * 100


@dataclass
class Stock:
    ticker: str
    earnings: list[EarningsReport] = field(default_factory=list)
    price_data: pd.DataFrame | None = None

    def add_earnings(self, report: EarningsReport) -> None:
        self.earnings.append(report)

    def set_price_data(self, frame: pd.DataFrame) -> None:
        if "Close" not in frame.columns:
            raise ValueError("price data must contain a 'Close' column")
        self.price_data = frame.sort_index()
