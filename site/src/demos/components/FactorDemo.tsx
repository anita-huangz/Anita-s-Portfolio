import { useMemo, useState } from "react";

import prices from "../../data/demos/factor-prices.json";
import { type FactorName, performanceMetrics, runBacktest } from "../lib/factor";
import { LineChart, type Series } from "./Chart";

const FACTORS: { id: FactorName; label: string }[] = [
  { id: "momentum", label: "Momentum" },
  { id: "low_volatility", label: "Low volatility" },
];

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const money = (v: number) => `$${Math.round(v).toLocaleString()}`;

export function FactorDemo() {
  const [selected, setSelected] = useState<FactorName[]>(["momentum"]);
  const [topN, setTopN] = useState(3);
  const [showBug, setShowBug] = useState(true);

  const { honest, cheating } = useMemo(() => {
    const options = {
      factors: selected.length ? selected : (["momentum"] as FactorName[]),
      topN,
      rebalanceEvery: 21,
      initialCash: 100000,
    };
    return {
      honest: runBacktest(prices, options),
      cheating: runBacktest(prices, { ...options, lookAhead: true }),
    };
  }, [selected, topN]);

  const honestMetrics = performanceMetrics(honest.nav);
  const cheatingMetrics = performanceMetrics(cheating.nav);

  // Downsampled: 1,005 points per line is more than the pixels can show.
  const step = 3;
  const toSeries = (nav: number[], label: string, color: string, dashed = false): Series => ({
    label,
    color,
    dashed,
    points: nav
      .map((y, x) => ({ x, y }))
      .filter((_, i) => i % step === 0 || i === nav.length - 1),
  });

  const series = [toSeries(honest.nav, "Point-in-time", "var(--se)")];
  if (showBug) {
    series.push(toSeries(cheating.nav, "With look-ahead bug", "var(--ds)", true));
  }

  const dateAt = (i: number) => prices.dates[Math.min(i, prices.dates.length - 1)]?.slice(0, 7) ?? "";

  const toggle = (id: FactorName) =>
    setSelected((cur) =>
      cur.includes(id) ? cur.filter((f) => f !== id) || [] : [...cur, id],
    );

  return (
    <div className="demo">
      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Factors</span>
          {FACTORS.map((f) => (
            <button
              key={f.id}
              className="chip"
              aria-pressed={selected.includes(f.id)}
              onClick={() => toggle(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="control">
          <span className="control-label">Hold top</span>
          {[1, 2, 3, 4].map((n) => (
            <button key={n} className="chip" aria-pressed={topN === n} onClick={() => setTopN(n)}>
              {n}
            </button>
          ))}
        </div>

        <div className="control">
          <button className="chip" aria-pressed={showBug} onClick={() => setShowBug((v) => !v)}>
            Show the look-ahead bug
          </button>
        </div>
      </div>

      <LineChart
        series={series}
        formatY={money}
        formatX={(i) => dateAt(Math.round(i))}
        yLabel="Portfolio value"
        height={280}
      />

      <div className="metric-row">
        <Metric label="Total return" a={pct(honestMetrics.totalReturn)}
                b={showBug ? pct(cheatingMetrics.totalReturn) : undefined} />
        <Metric label="Sharpe" a={honestMetrics.sharpeRatio.toFixed(2)}
                b={showBug ? cheatingMetrics.sharpeRatio.toFixed(2) : undefined} />
        <Metric label="Max drawdown" a={pct(honestMetrics.maxDrawdown)}
                b={showBug ? pct(cheatingMetrics.maxDrawdown) : undefined} />
        <Metric label="Rebalances" a={String(honest.rebalanceCount)} />
      </div>

      <p className="demo-note">
        Eight large-cap tech names, real daily closes from{" "}
        {prices.dates[0]} to {prices.dates[prices.dates.length - 1]}, rebalanced every 21
        trading days. The dashed line is the original bug: factors scored once from the
        <em> end</em> of the sample and reused at every rebalance, so the 2021 allocation
        was picked using 2024 returns. Same prices, same rules — the only difference is
        when the factors were measured.
      </p>
    </div>
  );
}

function Metric({ label, a, b }: { label: string; a: string; b?: string }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value" style={{ color: "var(--se)" }}>{a}</div>
      {b !== undefined && (
        <div className="metric-value secondary" style={{ color: "var(--ds)" }}>{b}</div>
      )}
    </div>
  );
}
