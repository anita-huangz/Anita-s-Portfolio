/**
 * Optional live price lookup through the Cloudflare Worker in `proxy/`.
 *
 * Absent the proxy the demos run on the tickers bundled with the site, which
 * is the default and always works. When `VITE_PRICE_PROXY` is configured the
 * demos additionally accept a ticker nobody shipped.
 */

export const PROXY_URL: string | undefined =
  import.meta.env.VITE_PRICE_PROXY || undefined;

export const liveLookupAvailable = Boolean(PROXY_URL);

export interface LiveSeries {
  ticker: string;
  dates: string[];
  closes: number[];
}

export class LiveLookupError extends Error {}

const TICKER = /^[A-Za-z][A-Za-z0-9.\-]{0,9}$/;

/** Fetch daily closes for one ticker. Throws with a readable reason. */
export async function fetchLiveSeries(
  ticker: string,
  range = "5y",
  signal?: AbortSignal,
): Promise<LiveSeries> {
  if (!PROXY_URL) {
    throw new LiveLookupError("Live lookup is not configured for this deployment.");
  }
  const symbol = ticker.trim().toUpperCase();
  // Validated here as well as in the Worker: a bad ticker should fail
  // instantly rather than after a round trip.
  if (!TICKER.test(symbol)) {
    throw new LiveLookupError(`"${ticker}" is not a plausible ticker symbol.`);
  }

  let response: Response;
  try {
    response = await fetch(
      `${PROXY_URL}/?ticker=${encodeURIComponent(symbol)}&range=${range}`,
      { signal },
    );
  } catch {
    throw new LiveLookupError("Could not reach the price proxy.");
  }

  const body = await response.json().catch(() => null);
  if (!response.ok) {
    throw new LiveLookupError(body?.error ?? `Lookup failed (${response.status}).`);
  }
  if (!body?.dates?.length) {
    throw new LiveLookupError(`No price history returned for ${symbol}.`);
  }
  return { ticker: symbol, dates: body.dates, closes: body.closes };
}

/**
 * Align a fetched series onto an existing date axis.
 *
 * The bundled prices define the axis. A live series covers a different span
 * and may miss sessions, so anything that does not line up is dropped rather
 * than forward-filled -- an invented price would flow straight into the factor
 * scores and quietly change the result.
 */
export function alignToDates(
  series: LiveSeries,
  dates: string[],
): number[] | null {
  const byDate = new Map(series.dates.map((d, i) => [d, series.closes[i]]));
  const aligned: number[] = [];
  for (const date of dates) {
    const value = byDate.get(date);
    if (value === undefined) return null;
    aligned.push(value);
  }
  return aligned;
}
