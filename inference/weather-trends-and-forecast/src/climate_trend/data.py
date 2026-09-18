"""Annual mean temperature for six cities, 1950-2024.

Reduced once from ERA5 daily reanalysis and committed as 14 KB, so the package
installs and the tests run with no network. Part-years are dropped: an annual
mean computed from 200 days is not comparable to one from 365, and quietly
including it puts a spurious kink at each end of the record.

The original scripts fetched a 90-day window and fitted a straight line through
daily maxima. Seventy-five years of annual means is the series a *trend*
question needs -- a slope fitted to three months of daily weather is measuring
the seasons.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).parent / "data" / "annual_mean_temperature.csv"

#: Open-Meteo's ERA5 archive. Allows browser requests, so the site's demo can
#: fetch any city live -- unusually for a data API.
SOURCE_URL = "https://archive-api.open-meteo.com/v1/era5"


class DataError(ValueError):
    """The file is not the dataset this package expects."""


@dataclass(frozen=True)
class Series:
    """One city's annual mean temperature."""

    city: str
    latitude: float
    year: np.ndarray
    temperature: np.ndarray

    def __len__(self) -> int:
        return len(self.year)

    @property
    def span(self) -> tuple[int, int]:
        return int(self.year.min()), int(self.year.max())

    @property
    def decades(self) -> np.ndarray:
        """Year, centred and expressed in decades.

        Centring matters for the intercept's interpretation and for the
        conditioning of the fit; decades because "degrees per decade" is the
        unit the result is quoted in, and rescaling afterwards is a step where
        factors of ten go missing.
        """
        return (self.year - self.year.mean()) / 10.0

    @property
    def year_to_year_sd(self) -> float:
        """Standard deviation of the first differences.

        The natural yardstick for a trend: if a decade of warming is smaller
        than one year's wobble, the trend is real but invisible in any single
        comparison.
        """
        return float(np.std(np.diff(self.temperature), ddof=1))


def load(path: Path | str = DATA) -> dict[str, Series]:
    """Every city in the file, keyed by name."""
    frame = pd.read_csv(path)
    missing = {"city", "year", "mean_c", "latitude"} - set(frame.columns)
    if missing:
        raise DataError(f"missing column(s): {sorted(missing)}")

    out: dict[str, Series] = {}
    for city, group in frame.groupby("city"):
        group = group.sort_values("year")
        if group["year"].duplicated().any():
            raise DataError(f"{city} has duplicate years")
        out[str(city)] = Series(
            city=str(city),
            latitude=float(group["latitude"].iloc[0]),
            year=group["year"].to_numpy(dtype=float),
            temperature=group["mean_c"].to_numpy(dtype=float),
        )
    if not out:
        raise DataError("no cities in the file")
    return out
