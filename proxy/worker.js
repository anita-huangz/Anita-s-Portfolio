/**
 * A price proxy for the portfolio demos.
 *
 * The demos are a static site, and the browser cannot call Yahoo directly --
 * it sends no CORS headers, so the request is blocked before it starts. This
 * Worker sits in between: it fetches on the server side, where CORS does not
 * apply, and returns the result with headers the browser will accept.
 *
 * Deliberately narrow. It proxies one upstream, one shape of request, and
 * rejects anything that is not a plausible ticker -- an open relay attached to
 * someone's domain is a liability, not a feature.
 */

const UPSTREAM = "https://query1.finance.yahoo.com/v8/finance/chart";

// Letters, digits, dots and dashes: enough for BRK-B and BF.B, and nothing
// that could be used to reach a different path on the upstream.
const TICKER = /^[A-Za-z][A-Za-z0-9.\-]{0,9}$/;

const ALLOWED_ORIGINS = new Set([
  "https://anita-huangz.github.io",
  "http://localhost:5173",
  "http://localhost:5177",
]);

const RANGES = new Set(["1y", "2y", "5y", "10y", "max"]);

function cors(origin) {
  const headers = {
    "Access-Control-Allow-Methods": "GET, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
    "Access-Control-Max-Age": "86400",
  };
  if (origin && ALLOWED_ORIGINS.has(origin)) {
    headers["Access-Control-Allow-Origin"] = origin;
    headers.Vary = "Origin";
  }
  return headers;
}

function json(body, status, origin, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...cors(origin), ...extra },
  });
}

export default {
  async fetch(request, env, ctx) {
    const origin = request.headers.get("Origin");

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: cors(origin) });
    }
    if (request.method !== "GET") {
      return json({ error: "method not allowed" }, 405, origin);
    }

    const url = new URL(request.url);
    const ticker = (url.searchParams.get("ticker") || "").toUpperCase();
    const range = url.searchParams.get("range") || "5y";

    if (!TICKER.test(ticker)) {
      return json({ error: `not a plausible ticker: ${ticker}` }, 400, origin);
    }
    if (!RANGES.has(range)) {
      return json({ error: `unsupported range: ${range}` }, 400, origin);
    }

    // Cache at the edge. Upstream rate limits are the real constraint here,
    // and daily closes do not change intraday.
    const cacheKey = new Request(`${url.origin}/p/${ticker}/${range}`, request);
    const cache = caches.default;
    const hit = await cache.match(cacheKey);
    if (hit) return hit;

    let upstream;
    try {
      upstream = await fetch(`${UPSTREAM}/${ticker}?interval=1d&range=${range}`, {
        headers: { "User-Agent": "Mozilla/5.0 (compatible; portfolio-demo/1.0)" },
      });
    } catch (e) {
      return json({ error: `upstream unreachable: ${e.message}` }, 502, origin);
    }

    if (!upstream.ok) {
      return json({ error: `upstream returned ${upstream.status}` }, 502, origin);
    }

    const payload = await upstream.json();
    const result = payload?.chart?.result?.[0];
    if (!result) {
      return json({ error: `no data for ${ticker}` }, 404, origin);
    }

    // Return only what the demo needs, rather than proxying the whole payload.
    const stamps = result.timestamp || [];
    const closes = result.indicators?.quote?.[0]?.close || [];
    const dates = [];
    const values = [];
    for (let i = 0; i < stamps.length; i++) {
      if (closes[i] == null) continue; // halted sessions come back null
      dates.push(new Date(stamps[i] * 1000).toISOString().slice(0, 10));
      values.push(Math.round(closes[i] * 100) / 100);
    }

    if (values.length === 0) {
      return json({ error: `no usable closes for ${ticker}` }, 404, origin);
    }

    const response = json(
      { ticker, range, dates, closes: values, source: "Yahoo Finance" },
      200,
      origin,
      { "Cache-Control": "public, max-age=21600" }, // six hours
    );
    ctx.waitUntil(cache.put(cacheKey, response.clone()));
    return response;
  },
};
