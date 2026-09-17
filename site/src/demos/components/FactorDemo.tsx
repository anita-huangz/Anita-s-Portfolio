import { useMemo, useState } from "react";

import { type FactorName, type PriceData, performanceMetrics, runBacktest } from "../lib/factor";
import { alignToDates, type LiveSeries } from "../livePrices";
import { useDemoData } from "../useDemoData";
import { LiveTickerInput } from "./LiveTickerInput";
import { LineChart, type Series } from "./Chart";
import { Loading } from "./Loading";
import { TickerPicker } from "./TickerPicker";
import { Term } from "./Term";

interface PriceFile extends PriceData {
  sectors: Record<string, string[]>;
}

const FACTORS: { id: FactorName; label: string }[] = [
  { id: "momentum", label: "Momentum" },
  { id: "low_volatility", label: "Low volatility" },
];

const CADENCES = [
  { days: 5, label: "Weekly" },
  { days: 21, label: "Monthly" },
  { days: 63, label: "Quarterly" },
];

const DEFAULT_UNIVERSE = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ORCL"];

const pct = (v: number) => `${(v * 100).toFixed(1)}%`;
const money = (v: number) => `$${Math.round(v).toLocaleString()}`;

export function FactorDemo() {
  const data = useDemoData<PriceFile>(() => import("../../data/demos/factor-prices.json"));
  if (!data) return <Loading label="Loading six years of daily prices…" />;
  return <Configured data={data} />;
}

function Configured({ data }: { data: PriceFile }) {
  const [universe, setUniverse] = useState<string[]>(() =>
    DEFAULT_UNIVERSE.filter((t) => data.tickers.includes(t)),
  );
  const [factors, setFactors] = useState<FactorName[]>(["momentum"]);
  const [topN, setTopN] = useState(3);
  const [cadence, setCadence] = useState(21);
  const [showBug, setShowBug] = useState(true);
  const [range, setRange] = useState<[number, number]>(() => [0, data.dates.length - 1]);
  // Tickers fetched live sit alongside the bundled ones for this session.
  const [extra, setExtra] = useState<Record<string, number[]>>({});
  const [liveError, setLiveError] = useState<string | null>(null);

  const allTickers = useMemo(
    () => [...data.tickers, ...Object.keys(extra)],
    [data.tickers, extra],
  );
  const allCloses = useMemo(
    () => ({ ...data.closes, ...extra }),
    [data.closes, extra],
  );

  const addLive = (series: LiveSeries) => {
    // The bundled dates are the axis. A live series that does not cover them
    // is rejected rather than padded -- an invented price would flow straight
    // into the factor scores.
    const aligned = alignToDates(series, data.dates);
    if (!aligned) {
      setLiveError(
        `${series.ticker} does not have a close for every session in the bundled window, so it cannot be scored against the others.`,
      );
      return;
    }
    setLiveError(null);
    setExtra((cur) => ({ ...cur, [series.ticker]: aligned }));
    setUniverse((cur) => [...new Set([...cur, series.ticker])]);
  };

  // A backtest needs at least a momentum lookback of history before it can
  // rank anything, so a very short window produces a flat line.
  const [from, to] = range;
  const windowLength = to - from + 1;

  const sliced: PriceData = useMemo(
    () => ({
      dates: data.dates.slice(from, to + 1),
      tickers: universe,
      closes: Object.fromEntries(
        universe.map((t) => [t, allCloses[t].slice(from, to + 1)]),
      ),
    }),
    [data.dates, allCloses, universe, from, to],
  );

  const { honest, cheating } = useMemo(() => {
    const options = {
      factors: factors.length ? factors : (["momentum"] as FactorName[]),
      topN: Math.min(topN, universe.length),
      rebalanceEvery: cadence,
      initialCash: 100000,
    };
    return {
      honest: runBacktest(sliced, options),
      cheating: runBacktest(sliced, { ...options, lookAhead: true }),
    };
  }, [sliced, factors, topN, cadence, universe.length]);

  const honestMetrics = performanceMetrics(honest.nav);
  const cheatingMetrics = performanceMetrics(cheating.nav);

  // Keep roughly 350 plotted points regardless of the window length.
  const step = Math.max(1, Math.floor(honest.nav.length / 350));
  const toSeries = (nav: number[], label: string, color: string, dashed = false): Series => ({
    label,
    color,
    dashed,
    points: nav
      .map((y, x) => ({ x, y }))
      .filter((_, i) => i % step === 0 || i === nav.length - 1),
  });

  const series = [toSeries(honest.nav, "Point-in-time", "var(--se)")];
  if (showBug) series.push(toSeries(cheating.nav, "With look-ahead bug", "var(--ds)", true));

  const toggleFactor = (id: FactorName) =>
    setFactors((cur) => (cur.includes(id) ? cur.filter((f) => f !== id) : [...cur, id]));

  return (
    <div className="demo">
      <TickerPicker
        all={allTickers}
        sectors={data.sectors}
        selected={universe}
        onChange={setUniverse}
        min={2}
      />

      <LiveTickerInput
        onLoaded={addLive}
        hint="Universe limited to the 62 companies bundled with the site. Deploy the proxy in `proxy/` to add any ticker — a static page cannot call a market-data API directly, because the browser blocks the cross-origin request."
      />
      {liveError && <p className="live-error">{liveError}</p>}

      <div className="demo-controls">
        <div className="control">
          <span className="control-label"><Term id="factor">Factors</Term></span>
          {FACTORS.map((f) => (
            <button
              key={f.id}
              className="chip"
              aria-pressed={factors.includes(f.id)}
              onClick={() => toggleFactor(f.id)}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="control">
          <span className="control-label"><Term id="hold-top">Hold top</Term></span>
          {[1, 2, 3, 5, 8].map((n) => (
            <button
              key={n}
              className="chip"
              aria-pressed={topN === n}
              disabled={n > universe.length}
              onClick={() => setTopN(n)}
            >
              {n}
            </button>
          ))}
        </div>

        <div className="control">
          <span className="control-label"><Term id="rebalance">Rebalance</Term></span>
          {CADENCES.map((c) => (
            <button
              key={c.days}
              className="chip"
              aria-pressed={cadence === c.days}
              onClick={() => setCadence(c.days)}
            >
              {c.label}
            </button>
          ))}
        </div>

        <button className="chip" aria-pressed={showBug} onClick={() => setShowBug((v) => !v)}>
          Show the look-ahead bug
        </button>
      </div>

      <p className="demo-hint" style={{ margin: "-6px 0 12px" }}>
        <Term id="momentum" /> buys what has been rising;{" "}
        <Term id="low-volatility" /> buys what moves least. The toggle above
        reproduces a <Term id="look-ahead" /> over the same prices.
      </p>

      <div className="range">
        <span className="control-label">
          Window <strong>{data.dates[from]}</strong> to <strong>{data.dates[to]}</strong>{" "}
          <span className="muted">
            ({windowLength} <Term id="trading-day">trading days</Term>)
          </span>
        </span>
        <div className="range-sliders">
          <input
            type="range" min={0} max={data.dates.length - 2} value={from}
            aria-label="Start date"
            onChange={(e) => {
              const v = Number(e.target.value);
              setRange(([, end]) => [Math.min(v, end - 60), end]);
            }}
          />
          <input
            type="range" min={1} max={data.dates.length - 1} value={to}
            aria-label="End date"
            onChange={(e) => {
              const v = Number(e.target.value);
              setRange(([start]) => [start, Math.max(v, start + 60)]);
            }}
          />
        </div>
      </div>

      <LineChart
        series={series}
        formatY={money}
        formatX={(i) => sliced.dates[Math.min(Math.round(i), sliced.dates.length - 1)]?.slice(0, 7) ?? ""}
        yLabel="Portfolio value"
        height={280}
      />

      <p className="demo-hint">
        The line is the portfolio's <Term id="nav" /> over time — what a{" "}
        <Term id="backtest" /> of these rules would have been worth.
      </p>

      <div className="metric-row">
        <Metric label="Total return" term="total-return" a={pct(honestMetrics.totalReturn)}
                b={showBug ? pct(cheatingMetrics.totalReturn) : undefined} />
        <Metric label="Annualized" term="annualised" a={pct(honestMetrics.annualizedReturn)}
                b={showBug ? pct(cheatingMetrics.annualizedReturn) : undefined} />
        <Metric label="Sharpe" term="sharpe" a={honestMetrics.sharpeRatio.toFixed(2)}
                b={showBug ? cheatingMetrics.sharpeRatio.toFixed(2) : undefined} />
        <Metric label="Max drawdown" term="drawdown" a={pct(honestMetrics.maxDrawdown)}
                b={showBug ? pct(cheatingMetrics.maxDrawdown) : undefined} />
        <Metric label="Rebalances" term="rebalance" a={String(honest.rebalanceCount)} />
      </div>

      {windowLength < 300 && (
        <p className="demo-warn">
          Momentum needs 252 trading days of history before it can rank anything, so a
          window this short spends most of its length unranked. Widen it to see the
          strategy actually trade.
        </p>
      )}

      <p className="demo-note">
        {universe.length} names, real daily closes, rebalanced{" "}
        {CADENCES.find((c) => c.days === cadence)!.label.toLowerCase()}. The dashed line
        is the original bug: factors scored once from the <em>end</em> of the window and
        reused at every rebalance, so the first allocation was picked using the last
        year's returns. Same prices, same rules — the only difference is when the factors
        were measured.
      </p>
    </div>
  );
}

function Metric({
  label,
  term,
  a,
  b,
}: {
  label: string;
  /** Glossary id, when the label is jargon. */
  term?: string;
  a: string;
  b?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {term ? <Term id={term}>{label}</Term> : label}
      </div>
      <div className="metric-value" style={{ color: "var(--se)" }}>{a}</div>
      {b !== undefined && (
        <div className="metric-value secondary" style={{ color: "var(--ds)" }}>{b}</div>
      )}
    </div>
  );
}
