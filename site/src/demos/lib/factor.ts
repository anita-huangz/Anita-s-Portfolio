/**
 * Port of `factor_sim`, for the interactive backtest.
 *
 * Checked in `factor.test.ts` against golden results the Python produced on
 * the same prices, for six factor/top-N combinations.
 */

export const TRADING_DAYS_PER_YEAR = 252;
export const MOMENTUM_LOOKBACK = 252;
export const VOLATILITY_WINDOW = 21;

export type FactorName = "momentum" | "low_volatility";

export interface PriceData {
  dates: string[];
  closes: Record<string, number[]>;
}

export interface BacktestOptions {
  factors: FactorName[];
  topN: number;
  rebalanceEvery: number;
  initialCash: number;
  /**
   * Reproduces the original bug: score once using exposures measured at the
   * end of the sample, then reuse that ranking at every rebalance.
   */
  lookAhead?: boolean;
}

export interface BacktestResult {
  dates: string[];
  nav: number[];
  weights: { date: string; weights: Record<string, number> }[];
  rebalanceCount: number;
}

export interface Metrics {
  totalReturn: number;
  annualizedReturn: number;
  volatility: number;
  sharpeRatio: number;
  maxDrawdown: number;
  tradingDays: number;
}

/** Cross-sectional z-score. A flat cross-section contributes nothing. */
export function zscore(values: Map<string, number>): Map<string, number> {
  const usable = [...values.values()].filter((v) => Number.isFinite(v));
  const out = new Map<string, number>();
  if (usable.length === 0) {
    for (const k of values.keys()) out.set(k, 0);
    return out;
  }
  const mean = usable.reduce((a, b) => a + b, 0) / usable.length;
  const variance =
    usable.reduce((a, b) => a + (b - mean) ** 2, 0) / usable.length;
  const sd = Math.sqrt(variance);
  for (const [k, v] of values) {
    out.set(k, !Number.isFinite(v) || sd === 0 ? 0 : (v - mean) / sd);
  }
  return out;
}

/**
 * Exposures using only prices up to and including `index`.
 *
 * This is the property the Python version originally lacked: it computed
 * exposures once from the whole sample, so every rebalance saw the future.
 */
export function exposuresAt(
  prices: PriceData,
  index: number,
  tickers: string[],
): { momentum: Map<string, number>; volatility: Map<string, number> } {
  const momentum = new Map<string, number>();
  const volatility = new Map<string, number>();

  for (const ticker of tickers) {
    const series = prices.closes[ticker];

    // Python guards on `len(history) > LOOKBACK`, and history is
    // prices[:index] inclusive, so its length is index + 1. Writing
    // `index > LOOKBACK` here starts a day late and changes the first
    // ranking of the backtest.
    if (index + 1 > MOMENTUM_LOOKBACK) {
      const past = series[index - MOMENTUM_LOOKBACK];
      momentum.set(ticker, past > 0 ? series[index] / past - 1 : NaN);
    } else {
      // Not enough history: undefined rather than a short-window return
      // mislabelled as twelve-month momentum.
      momentum.set(ticker, NaN);
    }

    if (index + 1 > VOLATILITY_WINDOW) {
      const returns: number[] = [];
      for (let i = index - VOLATILITY_WINDOW + 1; i <= index; i++) {
        returns.push(series[i] / series[i - 1] - 1);
      }
      const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
      const variance =
        returns.reduce((a, b) => a + (b - mean) ** 2, 0) / returns.length;
      volatility.set(ticker, Math.sqrt(variance) * Math.sqrt(TRADING_DAYS_PER_YEAR));
    } else {
      volatility.set(ticker, NaN);
    }
  }
  return { momentum, volatility };
}

function scoreUniverse(
  exposures: { momentum: Map<string, number>; volatility: Map<string, number> },
  factors: FactorName[],
  tickers: string[],
): Map<string, number> {
  const total = new Map<string, number>(tickers.map((t) => [t, 0]));

  for (const factor of factors) {
    const raw = new Map<string, number>();
    for (const ticker of tickers) {
      // Both oriented so higher is better; low-volatility is negated.
      raw.set(
        ticker,
        factor === "momentum"
          ? exposures.momentum.get(ticker)!
          : -exposures.volatility.get(ticker)!,
      );
    }
    for (const [ticker, z] of zscore(raw)) {
      total.set(ticker, (total.get(ticker) ?? 0) + z);
    }
  }
  return total;
}

/** Top N by score, equally weighted. Ties break on ticker, as in the Python. */
function optimize(scores: Map<string, number>, topN: number): Record<string, number> {
  const ranked = [...scores.entries()]
    .filter(([, v]) => Number.isFinite(v))
    .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))
    .slice(0, topN);

  if (ranked.length === 0) return {};
  const weight = 1 / ranked.length;
  return Object.fromEntries(ranked.map(([t]) => [t, weight]));
}

export function runBacktest(prices: PriceData, options: BacktestOptions): BacktestResult {
  const tickers = Object.keys(prices.closes);
  const { factors, topN, rebalanceEvery, initialCash, lookAhead = false } = options;

  let cash = initialCash;
  let holdings: Record<string, number> = {};
  const nav: number[] = [];
  const weightLog: { date: string; weights: Record<string, number> }[] = [];
  let rebalanceCount = 0;

  // The bug being reproduced: one ranking, computed from the final day.
  const frozenScores = lookAhead
    ? scoreUniverse(
        exposuresAt(prices, prices.dates.length - 1, tickers),
        factors,
        tickers,
      )
    : null;

  for (let i = 0; i < prices.dates.length; i++) {
    const priceAt: Record<string, number> = {};
    for (const t of tickers) priceAt[t] = prices.closes[t][i];

    if (i % rebalanceEvery === 0) {
      const scores =
        frozenScores ?? scoreUniverse(exposuresAt(prices, i, tickers), factors, tickers);
      const weights = optimize(scores, topN);

      if (Object.keys(weights).length > 0) {
        const total =
          cash +
          Object.entries(holdings).reduce((sum, [t, s]) => sum + priceAt[t] * s, 0);
        holdings = {};
        for (const [t, w] of Object.entries(weights)) {
          holdings[t] = (w * total) / priceAt[t];
        }
        cash =
          total -
          Object.entries(holdings).reduce((sum, [t, s]) => sum + priceAt[t] * s, 0);
        weightLog.push({ date: prices.dates[i], weights });
        rebalanceCount += 1;
      }
    }

    nav.push(
      cash + Object.entries(holdings).reduce((sum, [t, s]) => sum + priceAt[t] * s, 0),
    );
  }

  return { dates: prices.dates, nav, weights: weightLog, rebalanceCount };
}

export function performanceMetrics(nav: number[]): Metrics {
  if (nav.length < 2) throw new Error("need at least two NAV observations");

  const returns: number[] = [];
  for (let i = 1; i < nav.length; i++) returns.push(nav[i] / nav[i - 1] - 1);

  const totalReturn = nav[nav.length - 1] / nav[0] - 1;
  const years = nav.length / TRADING_DAYS_PER_YEAR;
  const annualizedReturn = years > 0 ? (1 + totalReturn) ** (1 / years) - 1 : 0;

  const mean = returns.reduce((a, b) => a + b, 0) / returns.length;
  // Sample standard deviation (ddof=1), matching the Python.
  const variance =
    returns.reduce((a, b) => a + (b - mean) ** 2, 0) / (returns.length - 1);
  const sd = Math.sqrt(variance);
  const volatility = sd * Math.sqrt(TRADING_DAYS_PER_YEAR);

  let peak = nav[0];
  let maxDrawdown = 0;
  for (const value of nav) {
    peak = Math.max(peak, value);
    maxDrawdown = Math.max(maxDrawdown, (peak - value) / peak);
  }

  return {
    totalReturn,
    annualizedReturn,
    volatility,
    sharpeRatio: sd > 0 ? (mean / sd) * Math.sqrt(TRADING_DAYS_PER_YEAR) : 0,
    maxDrawdown,
    tradingDays: nav.length,
  };
}
