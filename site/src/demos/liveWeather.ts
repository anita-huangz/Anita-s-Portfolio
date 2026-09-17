/**
 * Live ERA5 lookup for any location.
 *
 * Unlike the market-data APIs, Open-Meteo sends permissive CORS headers, so
 * the browser can call it directly and no proxy is needed. That makes the
 * weather demo genuinely open-ended: the bundled cities are presets, not the
 * limit.
 */

const GEOCODE = "https://geocoding-api.open-meteo.com/v1/search";
const ARCHIVE = "https://archive-api.open-meteo.com/v1/era5";

/** ERA5 lags real time by about five days; a week back keeps the last year whole. */
const LAG_DAYS = 7;

export interface Place {
  name: string;
  country: string;
  admin?: string;
  lat: number;
  lon: number;
}

export interface CitySeries {
  lat: number;
  lon: number;
  annual: { year: number; temp: number }[];
  trend: {
    slope_per_decade: number;
    intercept: number;
    sigma: number;
    first_year: number;
    last_year: number;
  };
  projection: { year: number; temp: number }[];
  monthly: { month: number; temp: number }[];
  warming: number;
}

export class WeatherLookupError extends Error {}

export async function searchPlaces(query: string, signal?: AbortSignal): Promise<Place[]> {
  const url = `${GEOCODE}?name=${encodeURIComponent(query)}&count=5`;
  let response: Response;
  try {
    response = await fetch(url, { signal });
  } catch {
    throw new WeatherLookupError("Could not reach the geocoding service.");
  }
  if (!response.ok) throw new WeatherLookupError(`Place search failed (${response.status}).`);

  const body = await response.json();
  return (body.results ?? []).map((r: Record<string, unknown>) => ({
    name: String(r.name),
    country: String(r.country ?? ""),
    admin: r.admin1 ? String(r.admin1) : undefined,
    lat: Number(r.latitude),
    lon: Number(r.longitude),
  }));
}

/** Least squares slope and intercept. Mirrors the project's numpy polyfit. */
function linearFit(xs: number[], ys: number[]): [number, number] {
  const n = xs.length;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let num = 0, den = 0;
  for (let i = 0; i < n; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    den += (xs[i] - mx) ** 2;
  }
  const slope = den === 0 ? 0 : num / den;
  return [slope, my - slope * mx];
}

export async function fetchCitySeries(
  place: Place,
  startYear = 1950,
  projectionYears = 25,
  signal?: AbortSignal,
): Promise<CitySeries> {
  const end = new Date(Date.now() - LAG_DAYS * 86400_000).toISOString().slice(0, 10);
  const url =
    `${ARCHIVE}?latitude=${place.lat}&longitude=${place.lon}` +
    `&start_date=${startYear}-01-01&end_date=${end}` +
    `&daily=temperature_2m_mean&timezone=UTC`;

  let response: Response;
  try {
    response = await fetch(url, { signal });
  } catch {
    throw new WeatherLookupError("Could not reach the ERA5 archive.");
  }
  if (!response.ok) {
    throw new WeatherLookupError(
      response.status === 429
        ? "The archive is rate limiting; wait a moment and try again."
        : `Archive request failed (${response.status}).`,
    );
  }

  const daily = (await response.json()).daily;
  const times: string[] = daily?.time ?? [];
  const temps: (number | null)[] = daily?.temperature_2m_mean ?? [];
  if (times.length === 0) throw new WeatherLookupError("No data for that location.");

  const byYear = new Map<number, number[]>();
  const byMonth = new Map<number, number[]>();
  for (let i = 0; i < times.length; i++) {
    const t = temps[i];
    if (t === null || t === undefined) continue;
    const year = Number(times[i].slice(0, 4));
    const month = Number(times[i].slice(5, 7));
    (byYear.get(year) ?? byYear.set(year, []).get(year)!).push(t);
    (byMonth.get(month) ?? byMonth.set(month, []).get(month)!).push(t);
  }

  const mean = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  // Drop partial years at either end, or the trend tilts on incomplete data.
  const annual = [...byYear.entries()]
    .filter(([, vals]) => vals.length > 300)
    .sort((a, b) => a[0] - b[0])
    .map(([year, vals]) => ({ year, temp: Number(mean(vals).toFixed(3)) }));

  if (annual.length < 10) {
    throw new WeatherLookupError("Not enough complete years at that location.");
  }

  const years = annual.map((a) => a.year);
  const values = annual.map((a) => a.temp);
  const [slope, intercept] = linearFit(years, values);

  const resid = values.map((v, i) => v - (slope * years[i] + intercept));
  // ddof=2: two parameters were fitted, matching the Python.
  const sigma = Math.sqrt(
    resid.reduce((a, b) => a + b * b, 0) / Math.max(1, resid.length - 2),
  );

  const last = years[years.length - 1];
  return {
    lat: place.lat,
    lon: place.lon,
    annual,
    trend: {
      slope_per_decade: Number((slope * 10).toFixed(4)),
      intercept,
      sigma: Number(sigma.toFixed(4)),
      first_year: years[0],
      last_year: last,
    },
    projection: Array.from({ length: projectionYears }, (_, i) => {
      const year = last + 1 + i;
      return { year, temp: Number((slope * year + intercept).toFixed(3)) };
    }),
    monthly: [...byMonth.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([month, vals]) => ({ month, temp: Number(mean(vals).toFixed(2)) })),
    warming: Number((slope * (last - years[0])).toFixed(3)),
  };
}
