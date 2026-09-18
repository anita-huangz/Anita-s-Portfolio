import { useState } from "react";

import {
  type CitySeries,
  type Place,
  type TrendRow,
  WeatherLookupError,
  fetchCitySeries,
  searchPlaces,
} from "../liveWeather";
import { useDemoData } from "../useDemoData";
import { BarChart, LineChart, ScatterChart, type ScatterGroup, type Series } from "./Chart";
import { Loading } from "./Loading";
import { Term } from "./Term";

const pct = (v: number) => `${(v * 100).toFixed(2)}%`;

function Stat({
  label,
  value,
  tone,
  term,
}: {
  label: string;
  value: string;
  tone?: string;
  /** Glossary id, when the label is jargon. */
  term?: string;
}) {
  return (
    <div className="metric">
      <div className="metric-label">
        {term ? <Term id={term}>{label}</Term> : label}
      </div>
      <div className="metric-value" style={tone ? { color: tone } : undefined}>{value}</div>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Weather
// --------------------------------------------------------------------------- //

interface City {
  lat: number;
  lon: number;
  annual: { year: number; temp: number }[];
  fitted: { year: number; temp: number }[];
  trends: {
    ols: TrendRow;
    newey_west: TrendRow;
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

interface WeatherFile {
  source: string;
  source_url: string;
  bootstrap_draws: number;
  cities: Record<string, City>;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const METHOD_TERM: Record<string, string> = {
  ols: "confidence-interval",
  newey_west: "newey-west",
  bootstrap: "block-bootstrap",
  mann_kendall: "mann-kendall",
};

const METHOD_LABEL: Record<string, string> = {
  ols: "Ordinary least squares",
  newey_west: "Newey-West (HAC)",
  bootstrap: "Block bootstrap",
  mann_kendall: "Mann-Kendall / Sen",
};

const signed = (v: number, dp = 3) => `${v >= 0 ? "+" : ""}${v.toFixed(dp)}`;

export function WeatherDemo() {
  const data = useDemoData<WeatherFile>(() => import("../../data/demos/nb-weather.json"));
  const [city, setCity] = useState("Chicago");
  const [showProjection, setShowProjection] = useState(true);
  const [showTrend, setShowTrend] = useState(true);
  const [band, setBand] = useState<"newey_west" | "ols">("newey_west");
  const [startYear, setStartYear] = useState(1950);

  // Places looked up live sit alongside the bundled ones for this session.
  const [extra, setExtra] = useState<Record<string, City>>({});
  const [query, setQuery] = useState("");
  const [matches, setMatches] = useState<Place[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!data) return <Loading label="Loading 75 years of reanalysis…" />;

  const cities: Record<string, City> = { ...data.cities, ...extra };
  const names = Object.keys(cities);
  const active = cities[city] ?? cities[names[0]];
  const { first, last } = active.span;
  const ols = active.trends.ols;
  const hac = active.trends.newey_west;
  const auto = active.autocorrelation;
  const rows = (["ols", "newey_west", "bootstrap", "mann_kendall"] as const)
    .map((key) => ({ key: key as string, row: active.trends[key] }))
    .filter((r): r is { key: string; row: TrendRow } => Boolean(r.row));

  const search = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true); setError(null); setMatches(null);
    try {
      const found = await searchPlaces(query);
      if (found.length === 0) setError(`No place matched "${query}".`);
      else setMatches(found);
    } catch (exc) {
      setError(exc instanceof WeatherLookupError ? exc.message : "Search failed.");
    } finally {
      setBusy(false);
    }
  };

  const load = async (place: Place) => {
    setBusy(true); setError(null);
    const label = [place.name, place.admin, place.country].filter(Boolean).join(", ");
    try {
      const series: CitySeries = await fetchCitySeries(place, startYear);
      setExtra((cur) => ({ ...cur, [label]: series as City }));
      setCity(label);
      setMatches(null);
      setQuery("");
    } catch (exc) {
      setError(exc instanceof WeatherLookupError ? exc.message : "Lookup failed.");
    } finally {
      setBusy(false);
    }
  };

  const series: Series[] = [
    {
      label: `${city} annual mean`,
      color: "var(--ai)",
      points: active.annual.map((a) => ({ x: a.year, y: a.temp })),
    },
  ];
  if (showTrend) {
    series.push({
      label: "Fitted trend",
      color: "var(--ds)",
      points: active.fitted.map((f) => ({ x: f.year, y: f.temp })),
    });
  }
  if (showProjection) {
    // The band is the slope interval extended, so switching between OLS and
    // Newey-West visibly changes how much the projection fans out.
    const scale = band === "ols" ? ols : hac;
    const level = active.fitted[active.fitted.length - 1].temp;
    const edge = (slope: number) =>
      active.projection.map((p) => ({
        x: p.year,
        y: level + (slope * (p.year - last)) / 10,
      }));
    series.push(
      {
        label: "Projected",
        color: "var(--ds)",
        dashed: true,
        points: active.projection.map((p) => ({ x: p.year, y: p.temp })),
      },
      {
        label: `${band === "ols" ? "OLS" : "Newey-West"} upper`,
        color: "var(--muted)",
        dashed: true,
        points: edge(scale.high),
      },
      {
        label: `${band === "ols" ? "OLS" : "Newey-West"} lower`,
        color: "var(--muted)",
        dashed: true,
        points: edge(scale.low),
      },
    );
  }

  const ranked = names
    .map((n) => ({ name: n, rate: cities[n].trends.ols.slope }))
    .sort((a, b) => b.rate - a.rate);

  return (
    <div className="demo">
      <div className="demo-controls">
        <div className="control" role="group" aria-label="Place">
          <span className="control-label">Place</span>
          {names.map((n) => (
            <button key={n} className="chip" aria-pressed={city === n} onClick={() => setCity(n)}>
              {n}
            </button>
          ))}
        </div>
      </div>

      <form className="demo-controls" onSubmit={search}>
        <label className="control" style={{ flex: 1, minWidth: 220 }}>
          <span className="control-label">Any city on earth</span>
          <input
            className="demo-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Reykjavík, Nairobi, Ulaanbaatar…"
            spellCheck={false}
          />
        </label>
        <button className="chip" type="submit" disabled={busy || !query.trim()}>
          {busy ? "Working…" : "Search"}
        </button>
        <div className="control" role="group" aria-label="Start year">
          <span className="control-label">From year</span>
          {[1950, 1970, 1990].map((y) => (
            <button key={y} type="button" className="chip" aria-pressed={startYear === y}
                    onClick={() => setStartYear(y)}>
              {y}
            </button>
          ))}
        </div>
      </form>

      {error && <p className="live-error">{error}</p>}
      {matches && (
        <div className="demo-controls">
          <div className="control" role="group" aria-label="Search results">
            <span className="control-label">Did you mean</span>
            {matches.map((m) => (
              <button key={`${m.lat},${m.lon}`} className="chip" onClick={() => void load(m)}>
                {[m.name, m.admin, m.country].filter(Boolean).join(", ")}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="demo-controls">
        <div className="control" role="group" aria-label="Chart layers">
          <button className="chip" aria-pressed={showTrend} onClick={() => setShowTrend((v) => !v)}>
            Trend line
          </button>
          <button className="chip" aria-pressed={showProjection}
                  onClick={() => setShowProjection((v) => !v)}>
            25-year projection
          </button>
        </div>
        <div className="control" role="group" aria-label="Uncertainty band">
          <span className="control-label">Band from</span>
          {(["ols", "newey_west"] as const).map((b) => (
            <button key={b} className="chip" aria-pressed={band === b} onClick={() => setBand(b)}>
              {b === "ols" ? "Naive interval" : "Autocorrelation-corrected"}
            </button>
          ))}
        </div>
      </div>

      <div className="metric-row">
        <Stat label="Years" value={`${first}–${last}`} />
        <Stat label="Warming rate" term="warming-rate"
              value={`${signed(ols.slope)} °C/decade`} tone="var(--ds)" />
        <Stat label="Honest 95% interval" term="newey-west"
              value={`${signed(hac.low)} to ${signed(hac.high)}`} />
        <Stat label="Total change over record"
              value={`${signed(active.warming, 2)} °C`} />
      </div>

      <LineChart
        series={series}
        height={280}
        formatX={(v) => String(Math.round(v))}
        formatY={(v) => `${v.toFixed(1)}°`}
        yLabel="Annual mean temperature (°C)"
      />

      <p className="demo-note" style={{ marginTop: 0 }}>
        ERA5 <Term id="reanalysis" />, {first} to {last}, fetched by latitude and
        longitude and averaged to annual means. Search any city and it is
        fetched live from the archive — Open-Meteo allows browser requests, so
        this needs no server of mine, and the same four tests run on it in the
        browser as ran on the presets in Python.
      </p>
      <p className="demo-hint">
        These run to {last}, so they will not match the project card's figures
        exactly: the package commits a fixed 1950–2024 extract so its tests can
        run offline, and one more warm year moves a 75-year slope slightly. The
        arithmetic is identical — `src/demos/trend.ts` is checked against the
        Python output for all six cities on every build.
      </p>

      <h5 className="demo-h" style={{ marginTop: 20 }}>
        Four ways to put an error bar on the same slope
      </h5>
      <div className="demo-table-wrap">
        <table className="demo-table">
          <thead>
            <tr>
              <th>Method</th>
              <th>Slope (°C/decade)</th>
              <th>Std. error</th>
              <th>95% interval</th>
              <th>Width</th>
              <th>p</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ key, row }) => (
              <tr key={key} className={key === "ols" ? undefined : "highlight"}>
                <td>
                  <Term id={METHOD_TERM[key]}>{METHOD_LABEL[key]}</Term>
                </td>
                <td>{signed(row.slope)}</td>
                <td className="dim">{row.se === null ? "—" : row.se.toFixed(4)}</td>
                <td>{signed(row.low)} to {signed(row.high)}</td>
                <td>{row.width.toFixed(3)}</td>
                <td>{row.p < 0.0001 ? "<0.0001" : row.p.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="metric-row">
        <Stat label="Interval widening" term="confidence-interval"
              value={active.interval_inflation ? `${active.interval_inflation.toFixed(2)}×` : "—"}
              tone="var(--ds)" />
        <Stat label="Residual lag-1" term="autocorrelation"
              value={signed(auto.lag1, 2)}
              tone={auto.correlated ? "var(--ds)" : undefined} />
        <Stat label="Effective sample size" term="effective-sample-size"
              value={`${auto.effective_n.toFixed(0)} of ${auto.n}`} />
        <Stat label="Year-to-year spread"
              value={`±${active.year_to_year_sd.toFixed(2)} °C`} />
      </div>

      <p className="demo-note">
        <strong>
          The slope is the same every way you compute it; the uncertainty is
          not.
        </strong>{" "}
        Ordinary least squares assumes each year is an independent draw. It is
        not — a warm year makes the next year more likely to be warm, and the
        residual lag-1 correlation here is {signed(auto.lag1, 2)}. Correcting
        for that widens the interval by{" "}
        {active.interval_inflation?.toFixed(2) ?? "—"}×, because{" "}
        {auto.n} annual readings carry about as much information as{" "}
        {auto.effective_n.toFixed(0)} independent ones.{" "}
        {hac.significant
          ? "The warming survives the correction and stays significant — which is the point of applying it rather than hoping."
          : "Once corrected, the trend no longer clears the significance bar."}{" "}
        The rank-based Mann-Kendall test agrees without assuming anything about
        the residuals at all.
      </p>
      <p className="demo-hint">
        Switch the band above between the naive and corrected intervals to see
        the difference on the chart. And note what the projection is: a straight
        line extended, not a climate model. Year-to-year variation is ±
        {active.year_to_year_sd.toFixed(2)} °C, larger than a decade of trend,
        so any single future year could land either side of the dashed line.
      </p>

      <div className="demo-split" style={{ marginTop: 16 }}>
        <div>
          <h5 className="demo-h">Warming rate by place (°C per decade)</h5>
          <BarChart
            bars={ranked.map((r) => ({
              label: r.name,
              value: r.rate,
              color: r.name === city ? "var(--ds)" : "var(--edge)",
              note: `${r.name}: ${signed(r.rate)} °C/decade`,
            }))}
            maxBars={14}
            formatValue={(v) => signed(v)}
          />
        </div>
        <div>
          <h5 className="demo-h">{city} seasonal shape</h5>
          <BarChart
            bars={active.monthly.map((m) => ({
              label: MONTHS[m.month - 1],
              value: m.temp,
              color: "var(--ai)",
            }))}
            maxBars={12}
            formatValue={(v) => `${v.toFixed(1)}°`}
          />
        </div>
      </div>
      <p className="demo-note">
        Add a few places and the pattern shows itself: mid- and high-latitude
        cities warm fastest, tropical ones slowest. That comparison only exists
        because the location is a parameter rather than a constant.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Stock-bond optimisation
// --------------------------------------------------------------------------- //

interface Performance {
  return: number;
  volatility: number;
  sharpe: number;
  excess_sharpe: number;
  max_drawdown: number;
  total_return?: number;
}

interface Rule {
  name: string;
  in_sample: Performance;
  out_of_sample: Performance;
  sharpe_shortfall: number;
  average_turnover: number;
  cost_drag: number;
  weight_instability: number;
  rebalances: number;
  final_weights: Record<string, number>;
  weight_path: Record<string, number | string>[];
}

interface FrontierPoint {
  return: number;
  volatility: number;
  sharpe: number;
  weights: Record<string, number>;
}

interface StockBond {
  generated: string;
  source: string;
  source_url: string;
  tickers: string[];
  names: Record<string, string>;
  cash_leg: string;
  start: string;
  end: string;
  days: number;
  risk_free: number;
  settings: { lookback: number; rebalance_every: number; cost_bps: number };
  shrinkage_intensity: number;
  condition_number: { sample: number; shrunk: number };
  assets: {
    ticker: string; name: string; return: number;
    volatility: number; sharpe: number;
  }[];
  correlation: Record<string, Record<string, number>>;
  rules: Rule[];
  frontier: FrontierPoint[];
  dates: string[];
  equity: Record<string, number[]>;
}

const RULE_COLORS: Record<string, string> = {
  "equal weight (1/N)": "var(--ai)",
  "minimum variance": "var(--ds)",
  "maximum Sharpe": "var(--se)",
  "risk parity": "var(--dv4)",
};

const RULE_TERM: Record<string, string> = {
  "equal weight (1/N)": "equal-weight",
  "minimum variance": "minimum-variance",
  "maximum Sharpe": "sharpe",
  "risk parity": "risk-parity",
};

export function StockBondDemo() {
  const data = useDemoData<StockBond>(() => import("../../data/demos/nb-stockbond.json"));
  const [view, setView] = useState<"realised" | "fitted">("realised");
  const [focus, setFocus] = useState<string | null>(null);
  if (!data) return <Loading label="Loading sixteen years of prices…" />;

  const rules = data.rules;
  const bestFitted = rules.reduce(
    (a, b) => (b.in_sample.excess_sharpe > a.in_sample.excess_sharpe ? b : a),
    rules[0],
  );
  const bestRealised = rules.reduce(
    (a, b) => (b.out_of_sample.excess_sharpe > a.out_of_sample.excess_sharpe ? b : a),
    rules[0],
  );
  const key = view === "realised" ? "out_of_sample" : "in_sample";

  const curves: Series[] = rules.map((r) => ({
    label: r.name,
    color: RULE_COLORS[r.name] ?? "var(--muted)",
    points: (data.equity[r.name] ?? []).map((v, i) => ({ x: i, y: v })),
  }));

  const frontierPoints: ScatterGroup[] = [
    {
      label: "In-sample frontier",
      color: "var(--edge)",
      points: data.frontier.map((f) => ({
        x: f.volatility,
        y: f.return,
        note: `in-sample: ${pct(f.return)} return at ${pct(f.volatility)} risk`,
      })),
    },
    {
      label: "What each rule actually earned",
      color: "var(--ds)",
      points: rules.map((r) => ({
        x: r.out_of_sample.volatility,
        y: r.out_of_sample.return,
        note: `${r.name}: realised ${pct(r.out_of_sample.return)} at ${pct(r.out_of_sample.volatility)}`,
      })),
    },
  ];

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Window" value={`${data.start} → ${data.end}`} />
        <Stat label="Trading days" value={data.days.toLocaleString()} />
        <Stat
          label="Best on the fitted numbers"
          term="in-sample"
          value={bestFitted.name}
          tone="var(--se)"
        />
        <Stat
          label="Best once actually run"
          term="out-of-sample"
          value={bestRealised.name}
          tone="var(--ds)"
        />
      </div>

      <p className="demo-note" style={{ marginTop: 0 }}>
        <strong>
          The rule that wins on paper is the one that loses in practice.
        </strong>{" "}
        Optimised over the whole history and scored on that same history,{" "}
        {bestFitted.name} looks best — excess Sharpe{" "}
        {bestFitted.in_sample.excess_sharpe.toFixed(2)}. Re-run so that each
        quarter's weights use only the previous{" "}
        {data.settings.lookback} trading days, and it realises{" "}
        {bestFitted.out_of_sample.excess_sharpe.toFixed(2)}. The honest winner
        is {bestRealised.name}, which estimates less and therefore has less to
        get wrong.
      </p>

      <div className="demo-controls">
        <div className="control" role="group" aria-label="Which numbers to show">
          <span className="control-label">Show</span>
          {(["realised", "fitted"] as const).map((v) => (
            <button key={v} className="chip" aria-pressed={view === v} onClick={() => setView(v)}>
              {v === "realised" ? "Out-of-sample (real)" : "In-sample (flattering)"}
            </button>
          ))}
        </div>
      </div>

      <div className="demo-table-wrap" style={{ marginTop: 12 }}>
        <table className="demo-table">
          <thead>
            <tr>
              <th>Allocation rule</th>
              <th>Return</th>
              <th><Term id="volatility">Risk</Term></th>
              <th><Term id="excess-sharpe">Sharpe over cash</Term></th>
              <th><Term id="drawdown">Worst fall</Term></th>
              <th><Term id="turnover">Turnover</Term></th>
              <th>Cost drag</th>
            </tr>
          </thead>
          <tbody>
            {rules.map((r) => {
              const p = r[key];
              return (
                <tr
                  key={r.name}
                  className={r.name === bestRealised.name && view === "realised" ? "highlight" : undefined}
                  onMouseEnter={() => setFocus(r.name)}
                  onMouseLeave={() => setFocus(null)}
                >
                  <td>
                    <Term id={RULE_TERM[r.name] ?? "backtest"}>{r.name}</Term>
                  </td>
                  <td>{pct(p.return)}</td>
                  <td>{pct(p.volatility)}</td>
                  <td
                    style={{
                      color:
                        p.excess_sharpe >= 0.5 ? "var(--se)"
                        : p.excess_sharpe < 0.2 ? "var(--ds)" : undefined,
                    }}
                  >
                    {p.excess_sharpe.toFixed(2)}
                  </td>
                  <td>{pct(p.max_drawdown)}</td>
                  <td className="dim">
                    {view === "realised" ? pct(r.average_turnover) : "—"}
                  </td>
                  <td className="dim">
                    {view === "realised" ? `${pct(r.cost_drag)}/yr` : "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="demo-hint">
        Sharpe here is measured <em>over cash</em>. The plain return-to-risk
        ratio flatters anything that hides in Treasuries: minimum variance puts
        {" "}{pct(bestRealised.final_weights[data.cash_leg] ?? 0)} of the book in{" "}
        {data.cash_leg} and scores spectacularly on the raw number while earning
        almost nothing above what cash paid. Subtracting cash is what makes the
        column comparable.
      </p>

      <h5 className="demo-h" style={{ marginTop: 20 }}>
        Growth of £1, out of sample only
      </h5>
      <LineChart
        series={focus ? curves.filter((c) => c.label === focus) : curves}
        height={260}
        formatX={(v) => data.dates[Math.round(v)] ?? ""}
        formatY={(v) => v.toFixed(2)}
        yLabel="Value of 1 invested"
      />
      <p className="demo-hint">
        Every point uses weights chosen before that day, rebalanced every{" "}
        {data.settings.rebalance_every} trading days at{" "}
        {data.settings.cost_bps} bps one-way. Hover a row above to isolate a
        rule.
      </p>

      <div className="demo-split" style={{ marginTop: 20 }}>
        <div>
          <h5 className="demo-h">
            The <Term id="frontier">efficient frontier</Term> is a picture of
            estimation error
          </h5>
          <ScatterChart
            height={260}
            groups={frontierPoints}
            xLabel="Risk (annual volatility)"
            yLabel="Return"
            formatX={(v) => pct(v)}
            formatY={(v) => pct(v)}
          />
          <p className="demo-hint">
            The grey curve is the classic frontier, drawn by optimising against
            the full history. The red points are where the same rules actually
            landed when they were only allowed to see the past. The vertical
            distance between them is not a modelling detail — it is the entire
            value of the optimisation, and it is negative.
          </p>
        </div>
        <div>
          <h5 className="demo-h">Why: the weights will not sit still</h5>
          <BarChart
            maxBars={rules.length}
            bars={rules.map((r) => ({
              label: r.name,
              value: r.weight_instability,
              color: RULE_COLORS[r.name] ?? "var(--muted)",
              note: `${r.name}: average weight moves ${pct(r.weight_instability)} per rebalance`,
            }))}
            formatValue={(v) => pct(v)}
          />
          <p className="demo-hint">
            How far the average holding moves from one rebalance to the next.
            The assets did not change that much in three months — the estimates
            did. {bestFitted.name} reshuffles{" "}
            {(bestFitted.weight_instability / Math.max(bestRealised.weight_instability, 1e-9)).toFixed(0)}×
            more than {bestRealised.name}, and pays{" "}
            {pct(bestFitted.cost_drag)} a year in trading costs for it.
          </p>
          <div className="metric-row" style={{ marginTop: 10 }}>
            <Stat
              label="Shrinkage intensity"
              term="ledoit-wolf"
              value={data.shrinkage_intensity.toFixed(3)}
            />
            <Stat
              label="Condition number"
              term="condition-number"
              value={`${Math.round(data.condition_number.sample).toLocaleString()} → ${Math.round(data.condition_number.shrunk).toLocaleString()}`}
            />
          </div>
        </div>
      </div>

      <h5 className="demo-h" style={{ marginTop: 20 }}>
        The five building blocks
      </h5>
      <div className="demo-table-wrap">
        <table className="demo-table">
          <thead>
            <tr>
              <th><Term id="etf">ETF</Term></th>
              <th>What it holds</th>
              <th>Return</th>
              <th>Risk</th>
              <th>Return ÷ risk</th>
            </tr>
          </thead>
          <tbody>
            {data.assets.map((a) => (
              <tr key={a.ticker}>
                <td className="mono">{a.ticker}</td>
                <td className="dim">{a.name}</td>
                <td>{pct(a.return)}</td>
                <td>{pct(a.volatility)}</td>
                <td>{a.sharpe.toFixed(2)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="demo-note">
        Prices are daily adjusted closes from Yahoo Finance through{" "}
        {data.end} — adjusted, because dividends are most of the return on{" "}
        <Term id="treasuries">Treasuries</Term> and credit and a backtest on raw prices reports {data.cash_leg} as flat
        when it has been quietly paying out the whole time. This is the
        DeMiguel, Garlappi and Uppal result reproduced on current data: once
        estimation error is paid for out of the portfolio rather than assumed
        away, the clever optimiser does not beat splitting the money evenly.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Bitcoin LSTM
// --------------------------------------------------------------------------- //

interface Direction {
  rate: number | null;
  low: number | null;
  high: number | null;
  correct: number;
  total: number;
  abstained: number;
  abstention_rate: number | null;
  beats_coin_flip: boolean;
}

interface WalkRow {
  name: string;
  folds: number;
  mean_rmse: number;
  rmse_low: number;
  rmse_high: number;
  mean_return_r2: number;
  folds_beating_zero_r2: number;
  direction: Direction;
  per_fold: {
    fold: number;
    test_start: string;
    test_end: string;
    rmse: number;
    return_r2: number;
    direction: number | null;
  }[];
}

interface SplitRow {
  rmse: number;
  mae: number;
  mape: number;
  return_r2: number;
  direction: number | null;
  direction_low: number | null;
  direction_high: number | null;
  abstention_rate: number | null;
  beats_coin_flip: boolean;
}

interface Strategy {
  name: string;
  total_return: number;
  annualised: number;
  volatility: number;
  sharpe: number;
  max_drawdown: number;
  trades: number;
  time_in_market: number;
}

interface Bitcoin {
  generated: string;
  source: string;
  source_url: string;
  bars: number;
  first_date: string;
  last_date: string;
  settings: {
    train_fraction: number; min_train: number;
    test_size: number; cost_bps: number;
  };
  model: string;
  lookback: number;
  walk_forward: WalkRow[];
  single_split: Record<string, SplitRow | number | string> & {
    days: number; first: string; last: string;
  };
  diebold_mariano: {
    statistic: number; p: number; mean_loss_difference: number;
    observations: number; lag: number; significant: boolean; better: string;
  } | null;
  scaler_leak: {
    train_max: number; train_min: number; full_max: number; full_min: number;
    split_date: string; range_inflation: number; unseen_high_fraction: number;
  };
  strategies: Strategy[];
  series: {
    date: string; actual: number; naive: number; lstm: number; leaky: number;
  }[];
}

const SPLIT_NAMES = ["naive (t-1)", "LSTM (honest scaling)", "LSTM (leaky scaling)"];

export function BitcoinDemo() {
  const data = useDemoData<Bitcoin>(() => import("../../data/demos/nb-bitcoin.json"));
  const [tab, setTab] = useState<"walk" | "split" | "trade">("walk");
  const [showLeaky, setShowLeaky] = useState(true);
  if (!data) return <Loading label="Loading fourteen years of daily bars…" />;

  const dm = data.diebold_mariano;
  const leak = data.scaler_leak;
  const hold = data.strategies.find((s) => s.name === "buy and hold");
  const traded = data.strategies.filter((s) => s.name !== "buy and hold");
  const bestTrade = traded.reduce(
    (a, b) => (b.total_return > a.total_return ? b : a),
    traded[0],
  );
  const splits = SPLIT_NAMES
    .map((n) => ({ name: n, row: data.single_split[n] as SplitRow | undefined }))
    .filter((r): r is { name: string; row: SplitRow } => Boolean(r.row));

  return (
    <div className="demo">
      <div className="metric-row">
        <Stat label="Daily bars" value={data.bars.toLocaleString()} />
        <Stat label="Through" value={data.last_date} />
        <Stat
          label="Rolling test windows"
          term="walk-forward"
          value={`${data.walk_forward[0]?.folds ?? 0} folds`}
        />
        {dm && (
          <Stat
            label="LSTM vs naive"
            term="diebold-mariano"
            value={dm.better === "second" ? "naive wins" : dm.better === "first" ? "LSTM wins" : "tie"}
            tone={dm.better === "second" ? "var(--ds)" : "var(--se)"}
          />
        )}
      </div>

      {dm && (
        <p className="demo-note" style={{ marginTop: 0 }}>
          <strong>
            "Tomorrow equals today" beats the neural network, and not by a
            coincidence.
          </strong>{" "}
          A Diebold-Mariano test on the two forecasts' daily losses gives t ={" "}
          {dm.statistic.toFixed(1)}, p{" "}
          {dm.p < 0.001 ? "< 0.001" : `= ${dm.p.toFixed(3)}`} over{" "}
          {dm.observations.toLocaleString()} days — the gap is far larger than
          the noise in it. Comparing two RMSE numbers could not have told you
          that; both forecasts make their mistakes on the same days, and the
          test accounts for it.
        </p>
      )}

      <div className="demo-controls">
        <div className="control" role="group" aria-label="Which evaluation to show">
          <span className="control-label">Evaluate by</span>
          {([
            ["walk", "Walk-forward"],
            ["split", "Single split"],
            ["trade", "Trading it"],
          ] as const).map(([v, label]) => (
            <button key={v} className="chip" aria-pressed={tab === v} onClick={() => setTab(v)}>
              {label}
            </button>
          ))}
        </div>
      </div>

      {tab === "walk" && (
        <>
          <div className="demo-table-wrap" style={{ marginTop: 12 }}>
            <table className="demo-table">
              <thead>
                <tr>
                  <th>Forecaster</th>
                  <th><Term id="rmse">RMSE</Term> (mean)</th>
                  <th><Term id="return-r2">R² on returns</Term></th>
                  <th>Folds beating R²=0</th>
                  <th><Term id="directional-accuracy">Direction</Term></th>
                  <th><Term id="wilson-interval">95% interval</Term></th>
                </tr>
              </thead>
              <tbody>
                {data.walk_forward.map((w) => (
                  <tr key={w.name}>
                    <td>{w.name}</td>
                    <td>${Math.round(w.mean_rmse).toLocaleString()}</td>
                    <td style={{ color: w.mean_return_r2 > 0 ? "var(--se)" : "var(--ds)" }}>
                      {w.mean_return_r2.toFixed(4)}
                    </td>
                    <td>{w.folds_beating_zero_r2} / {w.folds}</td>
                    <td>
                      {w.direction.rate === null
                        ? <span className="dim">no call</span>
                        : pct(w.direction.rate)}
                    </td>
                    <td className="dim">
                      {w.direction.low === null || w.direction.high === null
                        ? `abstained on all ${w.direction.abstained.toLocaleString()} days`
                        : `${pct(w.direction.low)} – ${pct(w.direction.high)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="demo-note">
            <strong>
              No forecaster predicts the daily move better than assuming there
              is none.
            </strong>{" "}
            R² on returns is zero or negative for every one of them, across{" "}
            {data.walk_forward[0]?.folds ?? 0} rolling windows spanning different
            market regimes — negative means worse than not trying. The
            directional hit rates sit within a percent or two of a coin flip and
            their intervals straddle 50%.
          </p>
          <p className="demo-hint">
            Each row is a <Term id="baseline">baseline</Term> — a deliberately
            simple rule that anything more sophisticated has to beat before it
            has earned its complexity. The naive forecaster shows "no call" because predicting tomorrow =
            today implies no direction at all. Scoring that as 0% would be
            wrong — it is not a wrong call — and 50% would be generous, so the{" "}
            {data.walk_forward[0]?.direction.abstained.toLocaleString()}{" "}
            abstentions are reported separately instead of being folded into an
            accuracy figure.
          </p>
          <h5 className="demo-h" style={{ marginTop: 18 }}>
            Error by fold — why one split would have misled you
          </h5>
          <LineChart
            height={220}
            series={data.walk_forward.map((w, i) => ({
              label: w.name,
              color: ["var(--ai)", "var(--ds)", "var(--se)", "var(--dv4)"][i % 4],
              points: w.per_fold.map((f) => ({ x: f.fold, y: f.rmse })),
            }))}
            formatX={(v) => `fold ${v}`}
            formatY={(v) => `$${Math.round(v).toLocaleString()}`}
            yLabel="RMSE ($)"
          />
          <p className="demo-hint">
            RMSE ranges from ${Math.round(data.walk_forward[0].rmse_low).toLocaleString()} to $
            {Math.round(data.walk_forward[0].rmse_high).toLocaleString()} across
            folds for the same forecaster — a four-hundred-fold spread driven
            entirely by the price level in each window. Any single train/test
            split reports one point on this line and calls it the answer.
          </p>
        </>
      )}

      {tab === "split" && (
        <>
          <div className="demo-table-wrap" style={{ marginTop: 12 }}>
            <table className="demo-table">
              <thead>
                <tr>
                  <th>Forecast</th>
                  <th>RMSE</th>
                  <th><Term id="mape">MAPE</Term></th>
                  <th>R² on returns</th>
                  <th>Direction</th>
                </tr>
              </thead>
              <tbody>
                {splits.map(({ name, row }) => (
                  <tr key={name} className={name.includes("leaky") ? "highlight" : undefined}>
                    <td>{name}</td>
                    <td>${Math.round(row.rmse).toLocaleString()}</td>
                    <td>{row.mape.toFixed(2)}%</td>
                    <td>{row.return_r2.toFixed(4)}</td>
                    <td>
                      {row.direction === null
                        ? <span className="dim">no call</span>
                        : pct(row.direction)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="demo-note">
            <strong>
              The leaky row is the one a notebook would have published.
            </strong>{" "}
            <Term id="scaler-leak">Scaler leakage</Term>:{" "}
            Scaling prices into 0–1 using the maximum of the <em>whole</em>{" "}
            series lets the model see a high that had not happened yet. Done
            correctly, on training data only, the scale tops out at $
            {Math.round(leak.train_max).toLocaleString()} while the series later
            reaches ${Math.round(leak.full_max).toLocaleString()} —{" "}
            {pct(leak.unseen_high_fraction)} of the axis is territory the model
            never saw in training, and it cannot forecast into it.
          </p>

          <div className="demo-controls">
            <div className="control" role="group" aria-label="Series to plot">
              <button className="chip" aria-pressed={showLeaky} onClick={() => setShowLeaky((v) => !v)}>
                Show the leaky forecast
              </button>
            </div>
          </div>
          <LineChart
            height={260}
            series={[
              {
                label: "Actual",
                color: "var(--text)",
                points: data.series.map((p, i) => ({ x: i, y: p.actual })),
              },
              {
                label: "Naive (t-1)",
                color: "var(--muted)",
                dashed: true,
                points: data.series.map((p, i) => ({ x: i, y: p.naive })),
              },
              {
                label: "LSTM, honest scaling",
                color: "var(--ds)",
                points: data.series.map((p, i) => ({ x: i, y: p.lstm })),
              },
              ...(showLeaky
                ? [{
                    label: "LSTM, leaky scaling",
                    color: "var(--se)",
                    points: data.series.map((p, i) => ({ x: i, y: p.leaky })),
                  }]
                : []),
            ]}
            formatX={(v) => data.series[Math.round(v)]?.date ?? ""}
            formatY={(v) => `$${Math.round(v / 1000)}k`}
            yLabel="BTC close (USD)"
          />
          <p className="demo-hint">
            An <Term id="lstm">LSTM</Term> — {data.model} — with a{" "}
            {data.lookback}-day <Term id="lookback">lookback</Term>, on a single{" "}
            <Term id="train-test">train/test split</Term> at{" "}
            {pct(data.settings.train_fraction)}. The honest line flattens
            out below the actual price because the training scale caps it there.
            The leaky line tracks beautifully — and is worthless.
          </p>
        </>
      )}

      {tab === "trade" && (
        <>
          <div className="demo-table-wrap" style={{ marginTop: 12 }}>
            <table className="demo-table">
              <thead>
                <tr>
                  <th>Strategy</th>
                  <th><Term id="total-return">Total return</Term></th>
                  <th><Term id="sharpe">Sharpe</Term></th>
                  <th><Term id="drawdown">Worst fall</Term></th>
                  <th>Trades</th>
                  <th>Time invested</th>
                </tr>
              </thead>
              <tbody>
                {data.strategies.map((s) => (
                  <tr
                    key={s.name}
                    className={s.name === "buy and hold" ? "highlight" : undefined}
                  >
                    <td>
                      {s.name === "buy and hold"
                        ? <Term id="buy-and-hold">buy and hold</Term>
                        : s.name}
                    </td>
                    <td style={{ color: s.total_return > 0 ? "var(--se)" : "var(--ds)" }}>
                      {pct(s.total_return)}
                    </td>
                    <td>{s.sharpe.toFixed(2)}</td>
                    <td>{pct(s.max_drawdown)}</td>
                    <td>{s.trades.toLocaleString()}</td>
                    <td className="dim">{pct(s.time_in_market)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="demo-note">
            <strong>
              The only strategy that makes money is buy-and-hold wearing a
              disguise.
            </strong>{" "}
            {bestTrade && hold && (
              <>
                The best signal, {bestTrade.name}, returns{" "}
                {pct(bestTrade.total_return)} with {bestTrade.trades} trade
                {bestTrade.trades === 1 ? "" : "s"} — it went long and stayed
                long, which is buy-and-hold ({pct(hold.total_return)}) minus a
                commission.
              </>
            )}{" "}
            The forecasters that actually trade lose money to costs at{" "}
            {data.settings.cost_bps} bps a side. Two rows show zero trades:
            those forecasters never imply an up-move, so they never take a
            position — the naive one by construction, and the honestly-scaled
            LSTM because its training range caps it below the current price.
          </p>
          <p className="demo-hint">
            This is the test that matters and the one a price-prediction
            notebook usually skips. A model can track a chart convincingly, post
            a low MAPE, and still have nothing tradeable in it, because the
            level is easy and the change is not.
          </p>
        </>
      )}

      <p className="demo-note">
        Data: {data.source}, {data.first_date} to {data.last_date}.{" "}
        <a href={data.source_url} target="_blank" rel="noreferrer">
          Source
        </a>
        . Everything above is computed by the project's{" "}
        <code>btc_forecast</code> package, the same code the command line runs.
      </p>
    </div>
  );
}
