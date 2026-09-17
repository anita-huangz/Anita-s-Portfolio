import { useState } from "react";

import {
  type CitySeries,
  type Place,
  WeatherLookupError,
  fetchCitySeries,
  searchPlaces,
} from "../liveWeather";
import { useDemoData } from "../useDemoData";
import { BarChart, LineChart, ScatterChart, type ScatterGroup, type Series } from "./Chart";
import { Loading } from "./Loading";
import { Term } from "./Term";

const pct = (v: number) => `${(v * 100).toFixed(2)}%`;
const money = (v: number) => `$${Math.round(v).toLocaleString()}`;

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
  trend: {
    slope_per_decade: number;
    intercept: number;
    sigma: number;
    first_year: number;
    last_year: number;
  };
  projection: { year: number; temp: number }[];
  monthly: { month: number; temp: number }[];
  warming: number;
}

interface WeatherFile {
  source: string;
  source_url: string;
  cities: Record<string, City>;
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function WeatherDemo() {
  const data = useDemoData<WeatherFile>(() => import("../../data/demos/nb-weather.json"));
  const [city, setCity] = useState("Chicago");
  const [showProjection, setShowProjection] = useState(true);
  const [showTrend, setShowTrend] = useState(true);
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
  const { slope_per_decade, intercept, first_year, last_year } = active.trend;
  const slope = slope_per_decade / 10;

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
      points: [first_year, last_year].map((y) => ({ x: y, y: slope * y + intercept })),
    });
  }
  if (showProjection) {
    series.push({
      label: "Projected",
      color: "var(--ds)",
      dashed: true,
      points: active.projection.map((p) => ({ x: p.year, y: p.temp })),
    });
  }

  const ranked = names
    .map((n) => ({ name: n, rate: cities[n].trend.slope_per_decade }))
    .sort((a, b) => b.rate - a.rate);

  return (
    <div className="demo">
      <div className="demo-controls">
        <div className="control">
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
        <div className="control">
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
          <div className="control">
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
        <div className="control">
          <button className="chip" aria-pressed={showTrend} onClick={() => setShowTrend((v) => !v)}>
            Trend line
          </button>
          <button className="chip" aria-pressed={showProjection}
                  onClick={() => setShowProjection((v) => !v)}>
            25-year projection
          </button>
        </div>
      </div>

      <div className="metric-row">
        <Stat label="Years" value={`${first_year}–${last_year}`} />
        <Stat label="Warming rate" term="warming-rate"
              value={`${slope_per_decade >= 0 ? "+" : ""}${slope_per_decade.toFixed(3)} °C/decade`}
              tone="var(--ds)" />
        <Stat label="Total change over record"
              value={`${active.warming >= 0 ? "+" : ""}${active.warming.toFixed(2)} °C`} />
        <Stat label="Year-to-year spread" value={`±${active.trend.sigma.toFixed(2)} °C`} />
      </div>

      <LineChart
        series={series}
        height={280}
        formatX={(v) => String(Math.round(v))}
        formatY={(v) => `${v.toFixed(1)}°`}
        yLabel="Annual mean temperature (°C)"
      />

      <p className="demo-note" style={{ marginTop: 0 }}>
        ERA5 <Term id="reanalysis" />, {first_year} to {last_year}, fetched by
        latitude and longitude
        and averaged to annual means. Search any city and it is fetched live from the
        archive — Open-Meteo allows browser requests, so this needs no server of mine.
        The trend is ordinary least squares, the same fit the project's forecast script
        uses. Note what the projection is and is not: a straight line extended, not a
        climate model. Year-to-year variation is ±{active.trend.sigma.toFixed(2)} °C,
        larger than a decade of the trend, so any single future year could land either
        side of the dashed line.
      </p>

      <div className="demo-split" style={{ marginTop: 16 }}>
        <div>
          <h5 className="demo-h">Warming rate by place (°C per decade)</h5>
          <BarChart
            bars={ranked.map((r) => ({
              label: r.name,
              value: r.rate,
              color: r.name === city ? "var(--ds)" : "var(--edge)",
            }))}
            maxBars={14}
            formatValue={(v) => `${v >= 0 ? "+" : ""}${v.toFixed(3)}`}
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
        Add a few places and the pattern shows itself: mid- and high-latitude cities
        warm fastest, tropical ones slowest. That comparison only exists because the
        location is a parameter rather than a constant.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Stock-bond optimisation
// --------------------------------------------------------------------------- //

interface Allocation {
  sharpe_weight: number;
  weights: Record<string, number>;
  return: number;
  volatility: number;
  sharpe: number;
}

interface FrontierPoint {
  return: number;
  volatility: number;
  sharpe: number;
  weights: Record<string, number>;
}

interface StockBond {
  tickers: string[];
  names: Record<string, string>;
  start: string;
  end: string;
  risk_free: number;
  assets: { ticker: string; name: string; return: number; volatility: number; sharpe: number }[];
  correlation: Record<string, Record<string, number>>;
  sweep: Allocation[];
  frontier: FrontierPoint[];
  dates: string[];
  paths: Record<string, number[]>;
  notable: { max_sharpe: FrontierPoint; min_vol: FrontierPoint };
}

const PATH_COLORS: Record<string, string> = {
  "Max Sharpe": "var(--se)",
  "Min volatility": "var(--ai)",
  "Equal weight": "var(--dv4)",
  "100% SPY": "var(--ds)",
};

export function StockBondDemo() {
  const data = useDemoData<StockBond>(() => import("../../data/demos/nb-stockbond.json"));
  const [step, setStep] = useState(6);
  const [visible, setVisible] = useState<string[]>(["Max Sharpe", "100% SPY"]);
  if (!data) return <Loading label="Solving the optimisation…" />;

  const chosen = data.sweep[Math.min(step, data.sweep.length - 1)];

  const frontierGroups: ScatterGroup[] = [
    {
      label: "Efficient frontier",
      color: "var(--ai)",
      points: data.frontier.map((f) => ({
        x: f.volatility * 100,
        y: f.return * 100,
        note: `Sharpe ${f.sharpe.toFixed(2)}`,
      })),
    },
    {
      label: "Individual assets",
      color: "var(--ds)",
      points: data.assets.map((a) => ({
        x: a.volatility * 100,
        y: a.return * 100,
        note: `${a.ticker} — ${a.name}`,
      })),
    },
    {
      label: "Your allocation",
      color: "var(--se)",
      points: [{
        x: chosen.volatility * 100,
        y: chosen.return * 100,
        note: `Sharpe ${chosen.sharpe.toFixed(2)}`,
      }],
    },
  ];

  const navSeries: Series[] = Object.entries(data.paths)
    .filter(([name]) => visible.includes(name))
    .map(([name, path]) => ({
      label: name,
      color: PATH_COLORS[name] ?? "var(--muted)",
      points: path.map((v, i) => ({ x: i, y: v })),
    }));

  const held = Object.entries(chosen.weights)
    .filter(([, w]) => w > 0.005)
    .sort((a, b) => b[1] - a[1]);

  return (
    <div className="demo">
      <div className="range">
        <span className="control-label">
          <Term id="risk-preference">Risk preference</Term> — weight on the{" "}
          <Term id="sharpe">Sharpe</Term> term:{" "}
          <strong>{chosen.sharpe_weight}</strong>
          {chosen.sharpe_weight === 0 && " (pure minimum variance)"}
        </span>
        <input
          type="range" min={0} max={data.sweep.length - 1} value={step}
          aria-label="Risk preference"
          onChange={(e) => setStep(Number(e.target.value))}
        />
      </div>

      <p className="demo-hint">
        Five <Term id="etf">ETFs</Term> — US large caps, small caps, long and
        short <Term id="treasuries" />, and corporate bonds. The curve is the{" "}
        <Term id="frontier" />: the best return available at each level of
        bumpiness.
      </p>

      <div className="metric-row">
        <Stat label="Expected return" term="expected-return" value={pct(chosen.return)} tone="var(--se)" />
        <Stat label="Volatility" term="volatility" value={pct(chosen.volatility)} tone="var(--ds)" />
        <Stat label="Sharpe" term="sharpe" value={chosen.sharpe.toFixed(2)} />
        <Stat label="Holdings" value={String(held.length)} />
      </div>

      <h5 className="demo-h">What the optimiser buys at this preference</h5>
      <BarChart
        bars={held.map(([t, w]) => ({
          label: `${t} — ${data.names[t]}`,
          value: w,
          note: data.names[t],
        }))}
        formatValue={(v) => `${(v * 100).toFixed(1)}%`}
      />
      <p className="demo-note">
        At a Sharpe weight of 0 the objective is pure variance minimisation, and the
        answer is entirely {data.names["SHV"].toLowerCase()} — the lowest-volatility
        asset available. Raise the preference and the solver accepts volatility in
        exchange for return, moving into equities and long Treasuries. This is the
        sweep the project runs: not one optimal portfolio, but a family of them
        indexed by how much return the investor wants per unit of risk.
      </p>

      <h5 className="demo-h" style={{ marginTop: 20 }}>Risk and return</h5>
      <ScatterChart
        groups={frontierGroups}
        height={300}
        xLabel="Annualised volatility (%)"
        yLabel="Annualised return (%)"
        formatX={(v) => `${v.toFixed(1)}%`}
        formatY={(v) => `${v.toFixed(1)}%`}
      />
      <p className="demo-note" style={{ marginTop: 0 }}>
        The frontier is the best return available at each level of risk. Individual
        assets sit below and to the right of it — that gap is the whole value of
        diversifying. Your current allocation is marked in green.
      </p>

      <h5 className="demo-h" style={{ marginTop: 20 }}>What that would have returned</h5>
      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Compare</span>
          {Object.keys(data.paths).map((name) => (
            <button
              key={name} className="chip" aria-pressed={visible.includes(name)}
              onClick={() =>
                setVisible((cur) =>
                  cur.includes(name) ? cur.filter((n) => n !== name) : [...cur, name],
                )
              }
            >
              {name}
            </button>
          ))}
        </div>
      </div>
      <LineChart
        series={navSeries}
        height={260}
        formatY={money}
        formatX={(i) => data.dates[Math.min(Math.round(i), data.dates.length - 1)]?.slice(0, 7) ?? ""}
        yLabel="Value of $100"
      />
      <p className="demo-note">
        $100 invested at the start of {data.start.slice(0, 4)}. The max-Sharpe portfolio
        is not the highest-returning one — 100% SPY beats it outright — because Sharpe
        rewards return <em>per unit of risk</em>, and a heavily cash-weighted book takes
        very little. Which of these is "best" depends entirely on a preference the
        optimiser cannot supply.
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Bitcoin LSTM
// --------------------------------------------------------------------------- //

interface Bitcoin {
  lookback: number;
  model: string;
  train_days: number;
  test_days: number;
  first_date: string;
  last_date: string;
  metrics: {
    rmse: number; mae: number; mape: number;
    naive_rmse: number; directional_accuracy: number;
  };
  leaky_metrics: { rmse: number; mape: number; directional_accuracy: number };
  train_max: number;
  test_max: number;
  series: { date: string; actual: number; predicted: number; naive: number; leaky: number }[];
}

export function BitcoinDemo() {
  const data = useDemoData<Bitcoin>(() => import("../../data/demos/nb-bitcoin.json"));
  const [shown, setShown] = useState<string[]>(["actual", "predicted", "naive"]);
  const [window, setWindow] = useState<[number, number] | null>(null);
  if (!data) return <Loading label="Loading model predictions…" />;

  const [from, to] = window ?? [0, data.series.length - 1];
  const slice = data.series.slice(from, to + 1);

  // Recomputed over the visible window, so the error you read matches the
  // stretch of chart you are looking at rather than the whole test period.
  const errOf = (key: "predicted" | "leaky" | "naive") =>
    Math.sqrt(
      slice.reduce((sum, r) => sum + (r[key] - r.actual) ** 2, 0) / Math.max(1, slice.length),
    );
  const windowed = {
    lstm: errOf("predicted"),
    naive: errOf("naive"),
    leaky: errOf("leaky"),
  };

  const m = data.metrics;
  const options: { id: keyof Bitcoin["series"][number]; label: string; color: string; dashed?: boolean }[] = [
    { id: "actual", label: "Actual price", color: "var(--ai)" },
    { id: "predicted", label: "LSTM (honest scaling)", color: "var(--ds)" },
    { id: "leaky", label: "LSTM (leaky scaling)", color: "var(--dv4)", dashed: true },
    { id: "naive", label: "Naive: tomorrow = today", color: "var(--se)", dashed: true },
  ];

  const series: Series[] = options
    .filter((o) => shown.includes(o.id as string))
    .map((o) => ({
      label: o.label,
      color: o.color,
      dashed: o.dashed,
      points: slice.map((s, i) => ({ x: from + i, y: s[o.id] as number })),
    }));

  const ratio = windowed.naive > 0 ? windowed.lstm / windowed.naive : 0;

  return (
    <div className="demo">
      <p className="demo-hint">
        An <Term id="lstm" /> against the dumbest possible{" "}
        <Term id="baseline">naive baseline</Term>. Watch which one wins.
      </p>

      <div className="metric-row">
        <Stat label="Days shown" value={slice.length.toLocaleString()} />
        <Stat label="LSTM RMSE" term="rmse" value={money(windowed.lstm)} tone="var(--ds)" />
        <Stat label="Naive RMSE" term="baseline" value={money(windowed.naive)} tone="var(--se)" />
        <Stat label="Directional accuracy" term="directional-accuracy" value={`${m.directional_accuracy.toFixed(1)}%`}
              tone="var(--ds)" />
      </div>

      <div className="range">
        <span className="control-label">
          Window <strong>{slice[0]?.date}</strong> to{" "}
          <strong>{slice[slice.length - 1]?.date}</strong>
        </span>
        <div className="range-sliders">
          <input
            type="range" min={0} max={data.series.length - 2} value={from}
            aria-label="Window start"
            onChange={(e) => {
              const v = Number(e.target.value);
              setWindow((cur) => {
                const [, end] = cur ?? [0, data.series.length - 1];
                return [Math.min(v, end - 20), end];
              });
            }}
          />
          <input
            type="range" min={1} max={data.series.length - 1} value={to}
            aria-label="Window end"
            onChange={(e) => {
              const v = Number(e.target.value);
              setWindow((cur) => {
                const [start] = cur ?? [0, data.series.length - 1];
                return [start, Math.max(v, start + 20)];
              });
            }}
          />
        </div>
        {window && (
          <button className="chip" style={{ marginTop: 6 }} onClick={() => setWindow(null)}>
            Reset to full test period
          </button>
        )}
      </div>

      <p className="demo-warn">
        <strong>
          A one-line baseline beats this model by {ratio.toFixed(0)}×.
        </strong>{" "}
        Predicting "tomorrow's price equals today's" gives an RMSE of{" "}
        {money(windowed.naive)} over the window shown; the trained LSTM gives{" "}
        {money(windowed.lstm)}. And its
        directional accuracy is {m.directional_accuracy.toFixed(1)}% — a coin flip.
        The chart still looks convincing, which is exactly the trap: a line that
        tracks the level of a price series can carry no information about its
        <em> changes</em>, and only the change is tradeable.
      </p>

      <div className="demo-controls">
        <div className="control">
          <span className="control-label">Show</span>
          {options.map((o) => (
            <button
              key={o.id as string} className="chip"
              aria-pressed={shown.includes(o.id as string)}
              onClick={() =>
                setShown((cur) =>
                  cur.includes(o.id as string)
                    ? cur.filter((x) => x !== (o.id as string))
                    : [...cur, o.id as string],
                )
              }
            >
              {o.label}
            </button>
          ))}
        </div>
      </div>

      <LineChart
        series={series}
        height={300}
        formatY={money}
        formatX={(i) => data.series[Math.min(Math.round(i), data.series.length - 1)]?.date.slice(0, 7) ?? ""}
        yLabel="BTC/USD"
      />

      <h5 className="demo-h" style={{ marginTop: 18 }}>Why the scaling matters</h5>
      <BarChart
        bars={[
          { label: "Naive baseline", value: windowed.naive, color: "var(--se)" },
          { label: "LSTM, leaky scaling", value: windowed.leaky, color: "var(--dv4)" },
          { label: "LSTM, honest scaling", value: windowed.lstm, color: "var(--ds)" },
        ]}
        formatValue={money}
      />
      <p className="demo-note">
        The project saved the model but not its scaler, so the transform has to be
        rebuilt — and how you rebuild it changes the answer. Fitting MinMax on the
        whole series before splitting lets the transform see the test range's maximum,
        which flatters the model ({money(windowed.leaky)} against{" "}
        {money(windowed.lstm)}). Fitting on the training portion only is correct, and it is
        also harsher here: training tops out near {money(data.train_max)} while the
        test period reaches {money(data.test_max)}, so the model is asked to
        extrapolate well beyond anything it ever saw. Neither version beats the
        baseline, and neither predicts direction.
      </p>

      <div className="metric-row">
        <Stat label="Lookback window" term="lookback" value={`${data.lookback} days`} />
        <Stat label="Train / test days" term="train-test" value={`${data.train_days.toLocaleString()} / ${data.test_days.toLocaleString()}`} />
        <Stat label="MAPE" term="mape" value={`${m.mape.toFixed(1)}%`} />
      </div>
      <p className="demo-note">
        {data.model}. The lookback is {data.lookback} days, read from the saved model's
        own input shape — the project's README says 60. The real lesson is about
        framing: forecasting a price <em>level</em> is close to unfalsifiable, because
        yesterday's price is already an excellent predictor of today's. Forecasting
        returns instead gives a target where a model can actually be wrong, and where
        the naive baseline is 0%.
      </p>
    </div>
  );
}
