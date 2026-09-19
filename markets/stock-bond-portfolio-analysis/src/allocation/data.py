"""Daily adjusted closes for five ETFs, 2010-2026.

Adjusted closes, not raw ones: dividends are most of the return on bond ETFs,
and a backtest on unadjusted prices reports SHV -- a short-Treasury fund whose
price barely moves -- as flat when it has been quietly paying out the whole
time.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

PRICES = Path(__file__).parent / "data" / "etf_prices.csv"

#: What each ticker is, since "IWM" is not self-explanatory.
DESCRIPTIONS = {
    "SPY": "US large-cap equities",
    "IWM": "US small-cap equities",
    "TLT": "20+ year Treasuries",
    "LQD": "investment-grade corporate bonds",
    "SHV": "short-term Treasuries (cash-like)",
}

TRADING_DAYS = 252


class DataError(ValueError):
    """The price file is not what this package expects."""


@dataclass(frozen=True)
class Prices:
    frame: pd.DataFrame

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def tickers(self) -> list[str]:
        return list(self.frame.columns)

    @property
    def returns(self) -> pd.DataFrame:
        return self.frame.pct_change().dropna()

    def annualised_summary(self) -> pd.DataFrame:
        r = self.returns
        return pd.DataFrame(
            {
                "annual_return": r.mean() * TRADING_DAYS,
                "annual_vol": r.std(ddof=1) * np.sqrt(TRADING_DAYS),
                "sharpe": r.mean() / r.std(ddof=1) * np.sqrt(TRADING_DAYS),
            }
        )


def load(path: Path | str = PRICES) -> Prices:
    frame = pd.read_csv(path, parse_dates=["date"], index_col="date")
    if frame.empty:
        raise DataError("no rows")
    if not frame.index.is_monotonic_increasing:
        raise DataError("dates are not in order; every split here assumes they are")
    if (frame <= 0).to_numpy().any():
        raise DataError("non-positive price")
    return Prices(frame=frame)
