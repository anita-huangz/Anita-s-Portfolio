"""Weather: live ERA5 annual means, with the trend inference from `climate_trend`.

The fetch stays here because the site should show a record that runs to this
year, not the 2024 cut-off baked into the package. Everything downstream of the
fetch -- every slope, interval and p-value -- comes from the package, so the
chart and `python -m climate_trend` cannot drift apart.

What changed: the previous version fitted ordinary least squares and drew a
projection band from the residual standard deviation. Annual temperatures are
autocorrelated, so that interval is too narrow; the package's Newey-West and
moving-block-bootstrap intervals are the honest ones, and all three are emitted
here so the width difference is visible rather than asserted.
"""
from __future__ import annotations
import argparse, json, pathlib, sys, time
from datetime import date, timedelta
import numpy as np, pandas as pd, requests

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-science-projects/weather-trends-and-forecast/src"))

from climate_trend.data import SOURCE_URL, Series
from climate_trend.trend import (
    block_bootstrap,
    mann_kendall,
    newey_west,
    ordinary_least_squares,
    residual_autocorrelation,
)

OUT = ROOT / "site/src/data/demos"
# ERA5 reanalysis lags real time by roughly five days, so asking for today
# returns a truncated final year. Backing off a week keeps the last year whole.
ERA5_LAG_DAYS = 7
DEFAULT_START = "1950-01-01"
# A year needs this many daily observations before its mean is comparable to a
# full year's. Part-years at either end otherwise put a spurious kink there.
MIN_DAYS_IN_YEAR = 300


def default_end() -> str:
    return str(date.today() - timedelta(days=ERA5_LAG_DAYS))

CITIES = {
    "Chicago":  (41.88, -87.63),
    "New York": (40.71, -74.01),
    "London":   (51.51, -0.13),
    "Tokyo":    (35.68, 139.69),
    "Sydney":   (-33.87, 151.21),
    "Nairobi":  (-1.29, 36.82),
}

def fetch(lat: float, lon: float, attempts: int = 5) -> pd.DataFrame:
    """Fetch with backoff. Open-Meteo's free tier rate-limits a burst of
    seventy-five-year requests, and a 429 here is transient, not fatal."""
    for attempt in range(attempts):
        try:
            return _fetch_once(lat, lon)
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 429:
                wait = 20 * (attempt + 1)
                print(f"    rate limited; waiting {wait}s")
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("gave up after repeated rate limiting")


def _fetch_once(lat: float, lon: float) -> pd.DataFrame:
    r = requests.get(
        SOURCE_URL,
        params={
            "latitude": lat, "longitude": lon,
            "start_date": args.start, "end_date": args.end,
            "daily": "temperature_2m_mean",
            "timezone": "UTC",
        },
        timeout=120,
    )
    r.raise_for_status()
    d = r.json()["daily"]
    return pd.DataFrame(
        {"date": pd.to_datetime(d["time"]), "temp": d["temperature_2m_mean"]}
    ).dropna()


def maybe(value: float, places: int = 4) -> float | None:
    """`null` rather than NaN, which is not valid JSON.

    Mann-Kendall has no standard error to report -- it is a rank test, and its
    interval comes from the distribution of pairwise slopes rather than from a
    sampling variance. The package says so with NaN; the chart has to render
    that as a blank cell, not as a zero.
    """
    return None if value is None or not np.isfinite(value) else round(float(value), places)


def as_trend(trend) -> dict:
    """A Trend, flattened for the browser. Slopes are degrees per decade."""
    return {
        "method": trend.method,
        "slope": round(trend.slope, 4),
        "se": maybe(trend.standard_error),
        "p": round(trend.p_value, 6),
        "low": round(trend.low, 4),
        "high": round(trend.high, 4),
        "width": round(trend.width, 4),
        "significant": trend.significant,
    }


parser = argparse.ArgumentParser(description="Fetch ERA5 and fit temperature trends.")
parser.add_argument("--start", default=DEFAULT_START, help="YYYY-MM-DD")
parser.add_argument("--end", default=default_end(), help="YYYY-MM-DD (default: a week ago)")
parser.add_argument(
    "--cities",
    default=",".join(CITIES),
    help="Comma-separated subset of: " + ", ".join(CITIES),
)
parser.add_argument("--projection-years", type=int, default=25)
parser.add_argument("--bootstrap-draws", type=int, default=2000)
args = parser.parse_args()

wanted = [c.strip() for c in args.cities.split(",") if c.strip() in CITIES]
series = {}
for name in wanted:
    lat, lon = CITIES[name]
    df = fetch(lat, lon)
    df["year"] = df["date"].dt.year
    counts = df.groupby("year").size()
    annual = df.groupby("year")["temp"].mean()[counts >= MIN_DAYS_IN_YEAR]

    record = Series(
        city=name,
        latitude=lat,
        year=annual.index.to_numpy(dtype=float),
        temperature=annual.to_numpy(dtype=float),
    )

    ols = ordinary_least_squares(record)
    hac = newey_west(record)
    boot = block_bootstrap(record, draws=args.bootstrap_draws)
    mk = mann_kendall(record)
    auto = residual_autocorrelation(record)

    # The projection is drawn off the OLS line, but its band comes from the
    # Newey-West slope interval -- the uncertainty that actually applies to
    # extrapolating a trend, rather than the year-to-year scatter about it.
    first, last = record.span
    centre = record.year.mean()
    level = float(record.temperature.mean())
    future = np.arange(last + 1, last + 1 + args.projection_years)

    def project(
        slope_per_decade: float,
        years: np.ndarray,
        level: float = level,
        centre: float = centre,
    ) -> list[float]:
        """Temperature along a line of this slope through the record's centre.

        `level` and `centre` are bound as defaults rather than captured: they
        are rebound on every city, and a closure over them would be a trap for
        whoever next moves this call out of the loop.
        """
        return [
            round(level + slope_per_decade * (y - centre) / 10.0, 3) for y in years
        ]

    series[name] = {
        "lat": lat, "lon": lon,
        # Six decimals rather than three. The site re-runs this same inference
        # in TypeScript for cities the visitor searches for, and `trend.test.ts`
        # checks that port against these numbers. At three decimals the rounding
        # of the input alone moved the answers by ~1e-4, which would have forced
        # a tolerance loose enough to hide a real disagreement. 456 numbers.
        "annual": [
            {"year": int(y), "temp": round(float(t), 6)}
            for y, t in zip(record.year, record.temperature)
        ],
        "fitted": [
            {"year": int(y), "temp": t}
            for y, t in zip(record.year, project(ols.slope, record.year))
        ],
        "trends": {
            "ols": as_trend(ols),
            "newey_west": as_trend(hac),
            "bootstrap": as_trend(boot),
            "mann_kendall": as_trend(mk),
        },
        # How much wider honest inference makes the interval. Above 1 means the
        # naive OLS standard error was understating the uncertainty.
        "interval_inflation": round(hac.width / ols.width, 2) if ols.width else None,
        "autocorrelation": {
            "lag1": round(auto.lag1, 4),
            "p": round(auto.lag1_p_value, 5),
            "durbin_watson": round(auto.durbin_watson, 3),
            "effective_n": round(auto.effective_sample_size, 1),
            "n": auto.n,
            "correlated": auto.is_correlated,
            "inflation": round(auto.inflation, 2),
        },
        "year_to_year_sd": round(record.year_to_year_sd, 3),
        "span": {"first": first, "last": last, "years": len(record)},
        "projection": [
            {
                "year": int(y),
                "temp": t,
                "low": lo,
                "high": hi,
            }
            for y, t, lo, hi in zip(
                future,
                project(ols.slope, future),
                project(hac.low, future),
                project(hac.high, future),
            )
        ],
        "monthly": [
            {"month": int(m), "temp": round(float(t), 2)}
            for m, t in df.groupby(df["date"].dt.month)["temp"].mean().items()
        ],
        "warming": round(ols.slope * (last - first) / 10.0, 3),
    }
    print(
        f"  {name:<9} {first}-{last}  OLS {ols.slope:+.3f} "
        f"[{ols.low:+.3f},{ols.high:+.3f}]  HAC [{hac.low:+.3f},{hac.high:+.3f}]  "
        f"x{hac.width / ols.width:.2f} wider  MK p={mk.p_value:.1e}"
    )
    time.sleep(8)  # be a polite client rather than a burst

payload = {
    "generated": str(date.today()),
    "start": args.start,
    "end": args.end,
    "source": "Open-Meteo ERA5 reanalysis archive",
    "source_url": "https://open-meteo.com/en/docs/historical-weather-api",
    "units": "degrees C per decade",
    "bootstrap_draws": args.bootstrap_draws,
    "cities": series,
}
path = OUT / "nb-weather.json"
path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
print(f"  nb-weather.json  {path.stat().st_size/1024:.1f} KB")
