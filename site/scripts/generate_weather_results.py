"""Weather: real ERA5 reanalysis, annual trend, and a forward projection."""
from __future__ import annotations
import argparse, json, pathlib, time
from datetime import date, timedelta
import numpy as np, pandas as pd, requests

OUT = pathlib.Path("site/src/data/demos")
# ERA5 reanalysis lags real time by roughly five days, so asking for today
# returns a truncated final year. Backing off a week keeps the last year whole.
ERA5_LAG_DAYS = 7
DEFAULT_START = "1950-01-01"


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
        "https://archive-api.open-meteo.com/v1/era5",
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

parser = argparse.ArgumentParser(description="Fetch ERA5 and fit temperature trends.")
parser.add_argument("--start", default=DEFAULT_START, help="YYYY-MM-DD")
parser.add_argument("--end", default=default_end(), help="YYYY-MM-DD (default: a week ago)")
parser.add_argument(
    "--cities",
    default=",".join(CITIES),
    help="Comma-separated subset of: " + ", ".join(CITIES),
)
parser.add_argument("--projection-years", type=int, default=25)
args = parser.parse_args()

wanted = [c.strip() for c in args.cities.split(",") if c.strip() in CITIES]
series = {}
for name in wanted:
    lat, lon = CITIES[name]
    df = fetch(lat, lon)
    df["year"] = df["date"].dt.year
    annual = df.groupby("year")["temp"].mean()
    # Drop partial years at the ends so the trend is not tilted by them.
    counts = df.groupby("year").size()
    annual = annual[counts > 300]

    years = annual.index.to_numpy(dtype=float)
    temps = annual.to_numpy(dtype=float)
    # Ordinary least squares, the same fit the project's forecast script uses.
    slope, intercept = np.polyfit(years, temps, 1)

    # Residual spread, so the projection can carry an honest band instead of
    # a single confident line.
    resid = temps - (slope * years + intercept)
    sigma = float(resid.std(ddof=2))

    future = np.arange(years[-1] + 1, years[-1] + 1 + args.projection_years)
    monthly = df.groupby(df["date"].dt.month)["temp"].mean()

    series[name] = {
        "lat": lat, "lon": lon,
        "annual": [
            {"year": int(y), "temp": round(float(t), 3)} for y, t in zip(years, temps)
        ],
        "trend": {
            "slope_per_decade": round(float(slope) * 10, 4),
            "intercept": round(float(intercept), 4),
            "sigma": round(sigma, 4),
            "first_year": int(years[0]),
            "last_year": int(years[-1]),
        },
        "projection": [
            {"year": int(y), "temp": round(float(slope * y + intercept), 3)}
            for y in future
        ],
        "monthly": [
            {"month": int(m), "temp": round(float(t), 2)} for m, t in monthly.items()
        ],
        "warming": round(float(slope * (years[-1] - years[0])), 3),
    }
    print(f"  {name:<9} {int(years[0])}-{int(years[-1])}  "
          f"{slope*10:+.3f} C/decade  total {slope*(years[-1]-years[0]):+.2f} C")
    time.sleep(8)  # be a polite client rather than a burst

payload = {
    "generated": str(date.today()),
    "start": args.start,
    "end": args.end,
    "source": "Open-Meteo ERA5 reanalysis archive",
    "source_url": "https://open-meteo.com/en/docs/historical-weather-api",
    "cities": series,
}
path = OUT / "nb-weather.json"
path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
print(f"  nb-weather.json  {path.stat().st_size/1024:.1f} KB")
