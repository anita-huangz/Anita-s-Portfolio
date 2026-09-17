# Price proxy

A ~100-line Cloudflare Worker that lets the portfolio demos look up **any**
ticker instead of only the ones bundled with the site.

## Why it exists

The site is static. A browser cannot call Yahoo Finance directly — the
response carries no `Access-Control-Allow-Origin`, so the request fails before
it reaches the network:

```
yahoo chart  BLOCKED: Failed to fetch
stooq csv    BLOCKED: Failed to fetch
```

CORS is a browser rule, not a server one, so a request made *server-side* is
unaffected. The Worker fetches there and returns the result with headers the
browser accepts.

## Deploying

```bash
npm install -g wrangler
wrangler login
wrangler deploy          # from this directory
```

Free tier covers 100,000 requests a day, which is far more than a portfolio
site will ever see. Then point the site at it:

```bash
# site/.env.local, or a repository variable for the Pages build
VITE_PRICE_PROXY=https://<your-worker>.workers.dev
```

**Without it the demos still work** — they fall back to the 62 tickers bundled
with the site. The proxy upgrades them from "a good set of companies" to "any
company".

## Scope

Narrow on purpose. An open relay attached to your domain is a liability:

- one upstream, one request shape
- tickers must match `^[A-Za-z][A-Za-z0-9.\-]{0,9}$`, so the path cannot be
  steered elsewhere
- an origin allowlist
- responses cached at the edge for six hours, because upstream rate limits are
  the real constraint and daily closes do not change intraday
- only the fields the demo needs are returned, not the whole upstream payload
