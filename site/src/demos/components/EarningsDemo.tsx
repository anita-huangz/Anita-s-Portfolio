import { useMemo, useState } from "react";

import { useDemoData } from "../useDemoData";
import { ScatterChart, type ScatterGroup } from "./Chart";
import { Loading } from "./Loading";
import { Term } from "./Term";

interface Event {
  date: string;
  surprise: number;
  d1: number;
  d5: number;
  d10: number;
}

interface Series {
  ticker: string;
  correlation_1d: number | null;
  correlation_5d: number | null;
  events: Event[];
}

interface DriftFile {
  series: Series[];
}

type Horizon = "d1" | "d5" | "d10";

const HORIZONS: { id: Horizon; label: string }[] = [
  { id: "d1", label: "1 day" },
  { id: "d5", label: "5 days" },
  { id: "d10", label: "10 days" },
];

export function EarningsDemo() {
  const data = useDemoData<DriftFile>(() => import("../../data/demos/earnings-drift.json"));
  if (!data) return <Loading label="Loading earnings history…" />;
  return <Configured data={data} />;
}

/** Pearson correlation. Null below three pairs, where it carries no signal. */
function correlate(xs: number[], ys: number[]): number | null {
  if (xs.length < 3) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / xs.length;
  const my = ys.reduce((a, b) => a + b, 0) / ys.length;
  let num = 0, dx = 0, dy = 0;
  for (let i = 0; i < xs.length; i++) {
    num += (xs[i] - mx) * (ys[i] - my);
    dx += (xs[i] - mx) ** 2;
    dy += (ys[i] - my) ** 2;
  }
  const den = Math.sqrt(dx * dy);
  return den === 0 ? null : num / den;
}

function Configured({ data }: { data: DriftFile }) {
  const [ticker, setTicker] = useState("AAPL");
  const [horizon, setHorizon] = useState<Horizon>("d5");
  const [pooled, setPooled] = useState(false);
  const [filter, setFilter] = useState("");

  const tickers = useMemo(() => data.series.map((s) => s.ticker).sort(), [data]);
  const visible = useMemo(() => {
    const needle = filter.trim().toUpperCase();
    return needle ? tickers.filter((t) => t.startsWith(needle)) : tickers;
  }, [tickers, filter]);

  const active = data.series.find((s) => s.ticker === ticker) ?? data.series[0];

  const events = pooled ? data.series.flatMap((s) => s.events) : active.events;
  const correlation = correlate(
    events.map((e) => e.surprise),
    events.map((e) => e[horizon]),
  );

  const groups: ScatterGroup[] = [
    {
      label: pooled ? `All ${data.series.length} companies` : active.ticker,
      color: pooled ? "var(--ai)" : "var(--ds)",
      points: events.map((e) => ({ x: e.surprise, y: e[horizon] * 100, note: e.date })),
    },
  ];

  // Ranked so the interesting names are findable without clicking through 62.
  const ranked = useMemo(
    () =>
      [...data.series]
        .filter((s) => s.correlation_5d !== null)
        .sort((a, b) => Math.abs(b.correlation_5d!) - Math.abs(a.correlation_5d!))
        .slice(0, 5),
    [data],
  );

  return (
    <div className="demo">
      <div className="picker">
        <div className="picker-presets">
          <span className="control-label">Company</span>
          <button className="chip" aria-pressed={pooled} onClick={() => setPooled((v) => !v)}>
            Pool all {data.series.length}
          </button>
          {ranked.map((s) => (
            <button
              key={s.ticker}
              className="chip"
              aria-pressed={!pooled && ticker === s.ticker}
              onClick={() => {
                setTicker(s.ticker);
                setPooled(false);
              }}
              title={`5-day correlation ${s.correlation_5d!.toFixed(2)}`}
            >
              {s.ticker} {s.correlation_5d! > 0 ? "+" : ""}
              {s.correlation_5d!.toFixed(2)}
            </button>
          ))}
          <input
            className="picker-filter"
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="filter…"
            spellCheck={false}
            aria-label="Filter tickers"
          />
        </div>

        <div className="picker-grid">
          {visible.map((t) => (
            <button
              key={t}
              className="ticker"
              aria-pressed={!pooled && t === ticker}
              onClick={() => {
                setTicker(t);
                setPooled(false);
              }}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="demo-controls">
        <div className="control">
          <span className="control-label"><Term id="drift">Drift over</Term></span>
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
          <div className="metric-label"><Term id="earnings">Announcements</Term></div>
          <div className="metric-value">{events.length}</div>
        </div>
        <div className="metric">
          <div className="metric-label">
            <Term id="surprise">Surprise</Term> vs{" "}
            {HORIZONS.find((h) => h.id === horizon)!.label}{" "}
            <Term id="drift">drift</Term>
          </div>
          <div className="metric-value">
            {correlation === null ? "—" : correlation.toFixed(2)}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label"><Term id="surprise">Median surprise</Term></div>
          <div className="metric-value">
            {events.length
              ? `${[...events.map((e) => e.surprise)].sort((a, b) => a - b)[
                  Math.floor(events.length / 2)
                ].toFixed(1)}%`
              : "—"}
          </div>
        </div>
        <div className="metric">
          <div className="metric-label"><Term id="beat-rate">Beat rate</Term></div>
          <div className="metric-value">
            {events.length
              ? `${Math.round(
                  (events.filter((e) => e.surprise > 0).length / events.length) * 100,
                )}%`
              : "—"}
          </div>
        </div>
      </div>

      <p className="demo-note">
        Real reported-versus-estimated EPS and real daily closes across{" "}
        {data.series.length} companies. Each point is one announcement: how far the
        estimate was beaten on the x-axis, how far the stock moved afterwards on the
        y-axis. If <Term id="drift">post-earnings drift</Term> were a dependable
        effect the cloud would slope
        upward. Mostly it doesn't — pooling every company collapses the correlation
        toward zero, and the handful of names with a real slope are the interesting
        part. Announcements on non-<Term id="trading-day">trading days</Term> use
        the prior session's close.
      </p>
      <p className="demo-note">
        These are <em>raw</em> moves. The project also measures{" "}
        <Term id="abnormal" /> against a <Term id="benchmark" />, and splits
        announcements into surprise <Term id="quintile">quintiles</Term> with a{" "}
        <Term id="t-stat" /> on the spread between the top and bottom fifth —
        which is where the effect mostly stops being convincing.
      </p>
    </div>
  );
}
