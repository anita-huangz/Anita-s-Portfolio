import { useState } from "react";

import data from "../../data/demos/earnings-drift.json";
import { ScatterChart, type ScatterGroup } from "./Chart";

type Horizon = "d1" | "d5" | "d10";

const HORIZONS: { id: Horizon; label: string }[] = [
  { id: "d1", label: "1 day" },
  { id: "d5", label: "5 days" },
  { id: "d10", label: "10 days" },
];

// First three categorical slots: the only three that clear the all-pairs
// colour-separation floor, which is what a scatter needs.
const COLORS = ["var(--ai)", "var(--ds)", "var(--se)", "var(--dv4)"];

export function EarningsDemo() {
  const [horizon, setHorizon] = useState<Horizon>("d5");
  const [ticker, setTicker] = useState<string>(data.series[0].ticker);

  const active = data.series.find((s) => s.ticker === ticker) ?? data.series[0];
  const correlation = horizon === "d1" ? active.correlation_1d : active.correlation_5d;

  const groups: ScatterGroup[] = [
    {
      label: active.ticker,
      color: COLORS[data.series.findIndex((s) => s.ticker === ticker) % COLORS.length],
      points: active.events.map((e) => ({
        x: e.surprise,
        y: e[horizon] * 100,
        note: e.date,
      })),
    },
  ];

  return (
    <div className="demo">
      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Company</span>
          {data.series.map((s) => (
            <button
              key={s.ticker}
              className="chip"
              aria-pressed={s.ticker === ticker}
              onClick={() => setTicker(s.ticker)}
            >
              {s.ticker}
            </button>
          ))}
        </div>
        <div className="control">
          <span className="control-label">Drift over</span>
          {HORIZONS.map((h) => (
            <button
              key={h.id}
              className="chip"
              aria-pressed={horizon === h.id}
              onClick={() => setHorizon(h.id)}
            >
              {h.label}
            </button>
          ))}
        </div>
      </div>

      <ScatterChart
        groups={groups}
        xLabel="Earnings surprise (%)"
        yLabel={`Return over ${HORIZONS.find((h) => h.id === horizon)!.label} (%)`}
        formatX={(v) => `${v.toFixed(0)}%`}
        formatY={(v) => `${v.toFixed(0)}%`}
      />

      <div className="metric-row">
        <div className="metric">
          <div className="metric-label">Events</div>
          <div className="metric-value">{active.events.length}</div>
        </div>
        <div className="metric">
          <div className="metric-label">Surprise vs 1-day drift</div>
          <div className="metric-value">
            {active.correlation_1d === null ? "—" : active.correlation_1d.toFixed(2)}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label">Surprise vs 5-day drift</div>
          <div className="metric-value">
            {active.correlation_5d === null ? "—" : active.correlation_5d.toFixed(2)}
          </div>
        </div>
      </div>

      <p className="demo-note">
        Real reported-versus-estimated EPS and real daily closes. Each point is one
        announcement: how far the estimate was beaten on the x-axis, how far the stock
        moved afterwards on the y-axis. If post-earnings drift were a reliable effect the
        cloud would slope upward — mostly it doesn't, and the correlation
        {correlation !== null && ` (${correlation.toFixed(2)} here)`} is the honest
        summary. Announcements on non-trading days use the prior session's close.
      </p>
    </div>
  );
}
