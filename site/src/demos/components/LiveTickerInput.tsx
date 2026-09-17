import { useState } from "react";

import { LiveLookupError, fetchLiveSeries, liveLookupAvailable } from "../livePrices";
import type { LiveSeries } from "../livePrices";

interface Props {
  onLoaded: (series: LiveSeries) => void;
  /** Explains what happens without the proxy, so the absence is not a mystery. */
  hint?: string;
}

export function LiveTickerInput({ onLoaded, hint }: Props) {
  const [symbol, setSymbol] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!liveLookupAvailable) {
    return (
      <p className="demo-note live-off">
        {hint ??
          "Showing the companies bundled with the site. Live lookup for any ticker needs the price proxy in `proxy/` deployed — a static page cannot call a market-data API directly, because the browser blocks the cross-origin request."}
      </p>
    );
  }

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      onLoaded(await fetchLiveSeries(symbol));
      setSymbol("");
    } catch (exc) {
      setError(exc instanceof LiveLookupError ? exc.message : "Lookup failed.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form className="live-lookup" onSubmit={submit}>
      <input
        className="picker-filter live-input"
        value={symbol}
        onChange={(e) => setSymbol(e.target.value)}
        placeholder="any ticker…"
        aria-label="Look up any ticker"
        spellCheck={false}
      />
      <button className="chip" type="submit" disabled={busy || !symbol.trim()}>
        {busy ? "Fetching…" : "Add"}
      </button>
      {error && <span className="live-error">{error}</span>}
    </form>
  );
}
