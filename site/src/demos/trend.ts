/**
 * Trend inference for the weather demo, ported from the `climate_trend` package.
 *
 * The bundled cities are analysed in Python and baked into `nb-weather.json`.
 * A city the visitor searches for is fetched in the browser, so the same
 * statistics have to exist here or a live city would silently fall back to a
 * bare least-squares line with an error bar that is too narrow — exactly the
 * mistake the project is about.
 *
 * `trend.test.ts` checks this port against the Python output for every bundled
 * city, so the two cannot drift apart unnoticed.
 */

export interface TrendEstimate {
  method: string;
  /** Degrees per decade. */
  slope: number;
  standardError: number | null;
  pValue: number;
  low: number;
  high: number;
  width: number;
  significant: boolean;
}

export interface AutocorrelationEstimate {
  lag1: number;
  durbinWatson: number;
  effectiveSampleSize: number;
  n: number;
  correlated: boolean;
  /** How much the error bar should widen, √(n / n_eff). */
  inflation: number;
}

/**
 * Year expressed in decades and centred on the mean.
 *
 * Centring conditions the fit and makes the intercept the mean level; decades
 * because "degrees per decade" is the unit the answer is quoted in, and
 * rescaling afterwards is where factors of ten go missing.
 */
function decades(years: number[]): number[] {
  const mean = years.reduce((a, b) => a + b, 0) / years.length;
  return years.map((y) => (y - mean) / 10);
}

/** Slope and intercept of `y` on `x` by least squares. */
function fit(x: number[], y: number[]): { slope: number; intercept: number } {
  const n = x.length;
  const mx = x.reduce((a, b) => a + b, 0) / n;
  const my = y.reduce((a, b) => a + b, 0) / n;
  let num = 0;
  let den = 0;
  for (let i = 0; i < n; i++) {
    num += (x[i] - mx) * (y[i] - my);
    den += (x[i] - mx) ** 2;
  }
  const slope = den === 0 ? 0 : num / den;
  return { slope, intercept: my - slope * mx };
}

/**
 * Two-sided p-value for Student's t.
 *
 * Via the regularised incomplete beta function, which is the relationship
 * `scipy.stats.t.sf` uses. Browsers have no t-distribution, and the normal
 * approximation is meaningfully wrong in the tail at these sample sizes.
 */
function studentTwoSided(t: number, df: number): number {
  const x = df / (df + t * t);
  return incompleteBeta(x, df / 2, 0.5);
}

/** Regularised incomplete beta I_x(a, b), by continued fraction. */
function incompleteBeta(x: number, a: number, b: number): number {
  if (x <= 0) return 0;
  if (x >= 1) return 1;
  const lbeta =
    logGamma(a + b) - logGamma(a) - logGamma(b) +
    a * Math.log(x) + b * Math.log(1 - x);
  const front = Math.exp(lbeta);
  // Lentz's algorithm; converges fastest on the side where x is small.
  const useLeft = x < (a + 1) / (a + b + 2);
  if (!useLeft) return 1 - incompleteBeta(1 - x, b, a);

  let f = 1, c = 1, d = 0;
  for (let i = 0; i <= 300; i++) {
    const m = Math.floor(i / 2);
    let numerator: number;
    if (i === 0) numerator = 1;
    else if (i % 2 === 0) {
      numerator = (m * (b - m) * x) / ((a + 2 * m - 1) * (a + 2 * m));
    } else {
      numerator = -(((a + m) * (a + b + m) * x) / ((a + 2 * m) * (a + 2 * m + 1)));
    }
    d = 1 + numerator * d;
    if (Math.abs(d) < 1e-30) d = 1e-30;
    d = 1 / d;
    c = 1 + numerator / c;
    if (Math.abs(c) < 1e-30) c = 1e-30;
    const step = c * d;
    f *= step;
    if (Math.abs(1 - step) < 1e-12) break;
  }
  return (front * (f - 1)) / a;
}

/** Lanczos approximation, accurate to ~1e-13 over the range used here. */
function logGamma(z: number): number {
  const g = [
    676.5203681218851, -1259.1392167224028, 771.32342877765313,
    -176.61502916214059, 12.507343278686905, -0.13857109526572012,
    9.9843695780195716e-6, 1.5056327351493116e-7,
  ];
  if (z < 0.5) {
    return Math.log(Math.PI / Math.sin(Math.PI * z)) - logGamma(1 - z);
  }
  const x = z - 1;
  let a = 0.99999999999980993;
  for (let i = 0; i < g.length; i++) a += g[i] / (x + i + 1);
  const t = x + g.length - 0.5;
  return 0.5 * Math.log(2 * Math.PI) + (x + 0.5) * Math.log(t) - t + Math.log(a);
}

/** Inverse Student t, by bisection on the two-sided tail. */
function studentCritical(df: number, alpha = 0.05): number {
  let lo = 0;
  let hi = 100;
  for (let i = 0; i < 200; i++) {
    const mid = (lo + hi) / 2;
    if (studentTwoSided(mid, df) > alpha) lo = mid;
    else hi = mid;
  }
  return (lo + hi) / 2;
}

function estimate(
  method: string,
  slope: number,
  se: number,
  df: number,
): TrendEstimate {
  const t = se > 0 ? slope / se : 0;
  const p = se > 0 ? studentTwoSided(Math.abs(t), df) : 1;
  const critical = studentCritical(df);
  const low = slope - critical * se;
  const high = slope + critical * se;
  return {
    method,
    slope,
    standardError: se,
    pValue: p,
    low,
    high,
    width: high - low,
    significant: p < 0.05,
  };
}

/** The textbook fit. Its error bar assumes independent years, which is false. */
export function ordinaryLeastSquares(years: number[], temps: number[]): TrendEstimate {
  const x = decades(years);
  const { slope, intercept } = fit(x, temps);
  const n = x.length;
  let rss = 0;
  for (let i = 0; i < n; i++) rss += (temps[i] - (slope * x[i] + intercept)) ** 2;
  const sigma2 = rss / (n - 2);
  const mx = x.reduce((a, b) => a + b, 0) / n;
  const sxx = x.reduce((a, v) => a + (v - mx) ** 2, 0);
  return estimate("OLS", slope, Math.sqrt(sigma2 / sxx), n - 2);
}

/**
 * OLS slope with the standard error corrected for autocorrelation.
 *
 * The sandwich estimator (X'X)⁻¹ S (X'X)⁻¹, where S accumulates the
 * autocovariance of the score up to `lag` under Bartlett weights. It can only
 * widen the interval when residuals are positively autocorrelated, which is
 * the normal case for temperature.
 */
export function neweyWest(
  years: number[],
  temps: number[],
  lag?: number,
): TrendEstimate {
  const x = decades(years);
  const n = x.length;
  const { slope, intercept } = fit(x, temps);
  const residuals = temps.map((t, i) => t - (slope * x[i] + intercept));
  // The usual 4(n/100)^(2/9) rule, which gives 4 for a 75-year record.
  const L = lag ?? Math.floor(4 * (n / 100) ** (2 / 9));

  // X is [1, x], so the score for observation i is [e_i, x_i e_i].
  const s0 = residuals;
  const s1 = residuals.map((e, i) => x[i] * e);

  const meat = [
    [0, 0],
    [0, 0],
  ];
  for (let i = 0; i < n; i++) {
    meat[0][0] += s0[i] * s0[i];
    meat[0][1] += s0[i] * s1[i];
    meat[1][0] += s1[i] * s0[i];
    meat[1][1] += s1[i] * s1[i];
  }
  for (let h = 1; h <= L; h++) {
    const w = 1 - h / (L + 1);
    const cross = [
      [0, 0],
      [0, 0],
    ];
    for (let i = h; i < n; i++) {
      cross[0][0] += s0[i] * s0[i - h];
      cross[0][1] += s0[i] * s1[i - h];
      cross[1][0] += s1[i] * s0[i - h];
      cross[1][1] += s1[i] * s1[i - h];
    }
    meat[0][0] += w * (cross[0][0] + cross[0][0]);
    meat[0][1] += w * (cross[0][1] + cross[1][0]);
    meat[1][0] += w * (cross[1][0] + cross[0][1]);
    meat[1][1] += w * (cross[1][1] + cross[1][1]);
  }

  // bread = (X'X)⁻¹ for X = [1, x].
  const sx = x.reduce((a, b) => a + b, 0);
  const sxx = x.reduce((a, b) => a + b * b, 0);
  const det = n * sxx - sx * sx;
  const bread = [
    [sxx / det, -sx / det],
    [-sx / det, n / det],
  ];

  // Only the [1][1] entry of bread·meat·bread is needed: the slope variance.
  const bm = [
    bread[1][0] * meat[0][0] + bread[1][1] * meat[1][0],
    bread[1][0] * meat[0][1] + bread[1][1] * meat[1][1],
  ];
  const variance = bm[0] * bread[0][1] + bm[1] * bread[1][1];
  return estimate(`Newey-West (lag ${L})`, slope, Math.sqrt(Math.max(variance, 0)), n - 2);
}

/**
 * Rank-based trend test with Sen's slope.
 *
 * Assumes nothing about the residual distribution, so it is the right
 * cross-check on a least-squares fit. Sen's slope is the median of all
 * pairwise slopes, and a single freak year barely moves it.
 */
export function mannKendall(years: number[], temps: number[]): TrendEstimate {
  const x = decades(years);
  const n = temps.length;

  let s = 0;
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) s += Math.sign(temps[j] - temps[i]);
  }

  const counts = new Map<number, number>();
  for (const v of temps) counts.set(v, (counts.get(v) ?? 0) + 1);
  let tieTerm = 0;
  for (const c of counts.values()) tieTerm += c * (c - 1) * (2 * c + 5);
  const variance = (n * (n - 1) * (2 * n + 5) - tieTerm) / 18;

  const z = s > 0 ? (s - 1) / Math.sqrt(variance)
    : s < 0 ? (s + 1) / Math.sqrt(variance)
    : 0;
  const p = 2 * (1 - normalCdf(Math.abs(z)));

  const pairs: number[] = [];
  for (let i = 0; i < n; i++) {
    for (let j = i + 1; j < n; j++) {
      if (x[j] !== x[i]) pairs.push((temps[j] - temps[i]) / (x[j] - x[i]));
    }
  }
  pairs.sort((a, b) => a - b);
  const mid = pairs.length / 2;
  const slope =
    pairs.length % 2 === 0
      ? (pairs[mid - 1] + pairs[mid]) / 2
      : pairs[Math.floor(mid)];

  // Distribution-free interval: the pair-slope order statistics either side
  // of the median, spaced by the normal critical value times the S deviation.
  const spread = 1.959963984540054 * Math.sqrt(variance);
  const clamp = (v: number) => Math.min(Math.max(Math.trunc(v), 0), pairs.length - 1);
  const low = pairs[clamp((pairs.length - spread) / 2 - 1)];
  const high = pairs[clamp((pairs.length + spread) / 2)];
  return {
    method: "Mann-Kendall / Sen",
    slope,
    // Rank-based: the interval comes from the pairwise slopes, not from a
    // sampling variance, so there is no standard error to report.
    standardError: null,
    pValue: p,
    low,
    high,
    width: high - low,
    significant: p < 0.05,
  };
}

/** Standard normal CDF via the error function (Abramowitz & Stegun 7.1.26). */
function normalCdf(z: number): number {
  const t = 1 / (1 + 0.2316419 * Math.abs(z));
  const d = 0.3989422804014327 * Math.exp((-z * z) / 2);
  const p =
    d * t * (0.319381530 + t * (-0.356563782 + t * (1.781477937 +
      t * (-1.821255978 + t * 1.330274429))));
  return z >= 0 ? 1 - p : p;
}

/** The assumption OLS depends on and temperature violates. */
export function residualAutocorrelation(
  years: number[],
  temps: number[],
): AutocorrelationEstimate {
  const x = decades(years);
  const n = x.length;
  const { slope, intercept } = fit(x, temps);
  const e = temps.map((t, i) => t - (slope * x[i] + intercept));

  const a = e.slice(0, -1);
  const b = e.slice(1);
  const ma = a.reduce((s, v) => s + v, 0) / a.length;
  const mb = b.reduce((s, v) => s + v, 0) / b.length;
  let cov = 0, va = 0, vb = 0;
  for (let i = 0; i < a.length; i++) {
    cov += (a[i] - ma) * (b[i] - mb);
    va += (a[i] - ma) ** 2;
    vb += (b[i] - mb) ** 2;
  }
  const lag1 = va > 0 && vb > 0 ? cov / Math.sqrt(va * vb) : 0;

  let diffSq = 0;
  for (let i = 1; i < n; i++) diffSq += (e[i] - e[i - 1]) ** 2;
  const rss = e.reduce((s, v) => s + v * v, 0);
  const durbinWatson = rss > 0 ? diffSq / rss : 0;

  const effective = lag1 > -1 ? (n * (1 - lag1)) / (1 + lag1) : n;
  const effectiveSampleSize = Math.max(effective, 1);
  return {
    lag1,
    durbinWatson,
    effectiveSampleSize,
    n,
    // A fixed Durbin-Watson cut-off is wrong at every n; this tests lag-1
    // directly against its own standard error under the null, 1/√n.
    correlated: Math.abs(lag1) > 1 / Math.sqrt(n),
    inflation: Math.sqrt(n / effectiveSampleSize),
  };
}
