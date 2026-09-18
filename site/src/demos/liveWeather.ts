/**
 * Live ERA5 lookup for any location.
 *
 * Unlike the market-data APIs, Open-Meteo sends permissive CORS headers, so
 * the browser can call it directly and no proxy is needed. That makes the
 * weather demo genuinely open-ended: the bundled cities are presets, not the
 * limit.
 */

import {
  mannKendall,
  neweyWest,
  ordinaryLeastSquares,
  residualAutocorrelation,
  type TrendEstimate,
} from "./trend";

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

/** A trend, in the shape the baked JSON uses, so the demo reads one type. */
export interface TrendRow {
  method: string;
  slope: number;
  se: number | null;
  p: number;
  low: number;
  high: number;
  width: number;
  significant: boolean;
}

export interface CitySeries {
  lat: number;
  lon: number;
  annual: { year: number; temp: number }[];
  fitted: { year: number; temp: number }[];
  trends: {
    ols: TrendRow;
    newey_west: TrendRow;
    /** Absent for live cities: 2,000 refits is not something to do in a tab. */
    bootstrap?: TrendRow;
    mann_kendall: TrendRow;
  };
  interval_inflation: number | null;
  autocorrelation: {
    lag1: number;
    p: number;
    durbin_watson: number;
    effective_n: number;
    n: number;
    correlated: boolean;
    inflation: number;
  };
  year_to_year_sd: number;
  span: { first: number; last: number; years: number };
  projection: { year: number; temp: number; low: number; high: number }[];
  monthly: { month: number; temp: number }[];
  warming: number;
}

function asRow(t: TrendEstimate): TrendRow {
  return {
    method: t.method,
    slope: t.slope,
    se: t.standardError,
    p: t.pValue,
    low: t.low,
    high: t.high,
    width: t.width,
    significant: t.significant,
  };
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

  // The same inference the bundled cities get, so a searched city is not
  // quietly analysed to a lower standard than a preset one.
  const ols = ordinaryLeastSquares(years, values);
  const hac = neweyWest(years, values);
  const mk = mannKendall(years, values);
  const auto = residualAutocorrelation(years, values);

  const first = years[0];
  const last = years[years.length - 1];
  const centre = years.reduce((a, b) => a + b, 0) / years.length;
  const level = values.reduce((a, b) => a + b, 0) / values.length;
  // Off the OLS line, with a band from the Newey-West slope interval — the
  // uncertainty that applies to extrapolating a trend, rather than the
  // year-to-year scatter around it.
  const at = (slopePerDecade: number, year: number) =>
    Number((level + (slopePerDecade * (year - centre)) / 10).toFixed(3));

  const diffs = values.slice(1).map((v, i) => v - values[i]);
  const dMean = diffs.reduce((a, b) => a + b, 0) / diffs.length;
  const yearToYear = Math.sqrt(
    diffs.reduce((a, b) => a + (b - dMean) ** 2, 0) / Math.max(1, diffs.length - 1),
  );

  return {
    lat: place.lat,
    lon: place.lon,
    annual,
    fitted: years.map((y) => ({ year: y, temp: at(ols.slope, y) })),
    trends: {
      ols: asRow(ols),
      newey_west: asRow(hac),
      mann_kendall: asRow(mk),
    },
    interval_inflation: ols.width > 0 ? Number((hac.width / ols.width).toFixed(2)) : null,
    autocorrelation: {
      lag1: Number(auto.lag1.toFixed(4)),
      // Lag-1 against its standard error under the null, 1/sqrt(n).
      p: Number((2 * (1 - normalCdfApprox(Math.abs(auto.lag1) * Math.sqrt(auto.n)))).toFixed(5)),
      durbin_watson: Number(auto.durbinWatson.toFixed(3)),
      effective_n: Number(auto.effectiveSampleSize.toFixed(1)),
      n: auto.n,
      correlated: auto.correlated,
      inflation: Number(auto.inflation.toFixed(2)),
    },
    year_to_year_sd: Number(yearToYear.toFixed(3)),
    span: { first, last, years: years.length },
    projection: Array.from({ length: projectionYears }, (_, i) => {
      const year = last + 1 + i;
      return {
        year,
        temp: at(ols.slope, year),
        low: at(hac.low, year),
        high: at(hac.high, year),
      };
    }),
    monthly: [...byMonth.entries()]
      .sort((a, b) => a[0] - b[0])
      .map(([month, vals]) => ({ month, temp: Number(mean(vals).toFixed(2)) })),
    warming: Number(((ols.slope * (last - first)) / 10).toFixed(3)),
  };
}

/** Standard normal CDF, for the lag-1 p-value above. */
function normalCdfApprox(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d = 0.3989422804014327 * Math.exp((-z * z) / 2);
  const p =
    d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 +
      t * (-1.821255978 + t * 1.330274429))));
  return z >= 0 ? 1 - p : p;
}
