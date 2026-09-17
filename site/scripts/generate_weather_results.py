"""Weather: real ERA5 reanalysis, annual trend, and a forward projection."""
from __future__ import annotations
import json, pathlib, time
import numpy as np, pandas as pd, requests

OUT = pathlib.Path("site/src/data/demos")
START, END = "1950-01-01", "2024-12-31"

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
            "start_date": START, "end_date": END,
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

series = {}
for name, (lat, lon) in CITIES.items():
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

    future = np.arange(years[-1] + 1, years[-1] + 26)
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
    "source": "Open-Meteo ERA5 reanalysis archive",
    "source_url": "https://open-meteo.com/en/docs/historical-weather-api",
    "cities": series,
}
path = OUT / "nb-weather.json"
path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
print(f"  nb-weather.json  {path.stat().st_size/1024:.1f} KB")
