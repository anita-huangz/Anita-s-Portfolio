import type { ResearchResult } from "../types";

/** Auto-compact large counts: 1,284 / 12.9K / 1.2M. */
function compact(n: number): string {
  if (n < 1000) return String(n);
  if (n < 10_000) return n.toLocaleString();
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K`;
  return `${(n / 1_000_000).toFixed(1)}M`;
}

function money(usd: number): string {
  if (usd === 0) return "$0";
  if (usd < 0.01) return `$${usd.toFixed(4)}`;
  return `$${usd.toFixed(2)}`;
}

function duration(ms: number): string {
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms / 1000).toFixed(1)}s`;
}

interface Props {
  result: ResearchResult | null;
}

/**
 * A stat row, not a chart: four single values with no trend to plot.
 * Values use proportional figures -- `tabular-nums` reads loose at this size.
 */
export function StatTiles({ result }: Props) {
  const usage = result?.usage;
  const cached = usage?.cache_read_input_tokens ?? 0;
  const total =
    (usage?.input_tokens ?? 0) +
    (usage?.output_tokens ?? 0) +
    cached +
    (usage?.cache_creation_input_tokens ?? 0);

  const tiles = [
    {
      label: "Tokens",
      value: result ? compact(total) : "—",
      sub: result ? `${compact(cached)} read from cache` : "input + output + cache",
    },
    {
      label: "Estimated cost",
      value: result ? money(result.estimated_cost_usd) : "—",
      sub: "at published per-model rates",
    },
    {
      label: "Latency",
      value: result ? duration(result.latency_ms) : "—",
      sub: "end to end, wall clock",
    },
    {
      label: "Tool calls",
      value: result ? String(result.tool_calls_made) : "—",
      sub: "EDGAR and price lookups",
    },
  ];

  return (
    <div className="tiles">
      {tiles.map((tile) => (
        <div className="tile" key={tile.label}>
          <div className="label">{tile.label}</div>
          <div className="value">{tile.value}</div>
          <div className="sub">{tile.sub}</div>
        </div>
      ))}
    </div>
  );
}
