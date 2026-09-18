"""Daily Bitcoin bars, and the returns that are the actual forecasting target.

The original notebook forecast the *price level* and reported RMSE in dollars.
That is the wrong target and the wrong metric, for a reason that is easy to
state and easy to miss: a price series is almost a random walk, so predicting
"tomorrow is roughly today" gets the level nearly right and tells you nothing.
Only the *change* is tradeable, and a level forecast can track the series
beautifully while carrying no information about changes at all.

So everything here is set up to ask the harder question. `log_returns` is the
target; the level is kept only to reconstruct prices for reporting.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DAILY = Path(__file__).parent / "data" / "btcusd_daily.csv"

#: The raw Kaggle file is minute trades. Reducing it to daily bars once, and
#: committing those, keeps the package installable and the tests fast --
#: 230 KB instead of 127 MB, and no decompression on every run.
RAW_MINUTE = Path(__file__).resolve().parents[2] / "data" / "btcusd_1-min_data.csv.zstd"


class DataError(ValueError):
    """The price file is not what this package expects."""


@dataclass(frozen=True)
class Prices:
    """Daily closes and their log returns, aligned."""

    frame: pd.DataFrame

    def __len__(self) -> int:
        return len(self.frame)

    @property
    def close(self) -> pd.Series:
        return self.frame["Close"]

    @property
    def log_returns(self) -> pd.Series:
        """`log(P_t / P_{t-1})`, with the first (undefined) day dropped.

        Log rather than simple returns so they add over time, which is what
        makes a multi-day horizon a sum rather than a product.
        """
        return np.log(self.close).diff().dropna()

    @property
    def dates(self) -> pd.DatetimeIndex:
        return pd.DatetimeIndex(self.frame.index)

    def slice(self, start: str | None = None, end: str | None = None) -> Prices:
        return Prices(self.frame.loc[start:end])


def load(path: Path | str = DAILY) -> Prices:
    """Read daily bars and check they are usable as a time series."""
    frame = pd.read_csv(path, parse_dates=["date"], index_col="date")
    missing = {"Open", "High", "Low", "Close"} - set(frame.columns)
    if missing:
        raise DataError(f"missing column(s): {sorted(missing)}")
    if not frame.index.is_monotonic_increasing:
        raise DataError("dates are not in order; every split here assumes they are")
    if frame.index.has_duplicates:
        raise DataError("duplicate dates")
    if (frame["Close"] <= 0).any():
        raise DataError("non-positive close; log returns would be undefined")
    return Prices(frame=frame)


def build_daily_from_minutes(
    source: Path | str = RAW_MINUTE, out: Path | str = DAILY
) -> Prices:
    """Regenerate the daily bars from the raw minute file.

    Kept so the committed CSV is reproducible rather than a mystery artifact.
    """
    import io

    import zstandard

    with open(source, "rb") as handle:
        reader = zstandard.ZstdDecompressor().stream_reader(handle)
        raw = pd.read_csv(
            io.TextIOWrapper(reader, "utf-8"),
            usecols=["Timestamp", "Open", "High", "Low", "Close", "Volume"],
        )

    stamped = raw.set_index(pd.to_datetime(raw["Timestamp"], unit="s", utc=True))
    daily = (
        stamped.drop(columns=["Timestamp"])
        .resample("D")
        .agg({"Open": "first", "High": "max", "Low": "min", "Close": "last",
              "Volume": "sum"})
        .dropna(subset=["Close"])
    )
    # Order matters: assigning `.date` replaces the index and drops its name,
    # so naming it first writes a CSV with a blank first header cell.
    daily.index = daily.index.date
    daily.index.name = "date"
    daily.round(2).to_csv(out, lineterminator="\n")
    return load(out)
