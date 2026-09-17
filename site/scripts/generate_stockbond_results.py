"""Stock-bond: the constrained optimisation, solved across risk preferences."""
from __future__ import annotations
import argparse, json, pathlib, warnings
from datetime import date
import numpy as np, pandas as pd, yfinance as yf
from scipy.optimize import minimize
warnings.filterwarnings("ignore")

OUT = pathlib.Path("site/src/data/demos")
TICKERS = ["SPY", "IWM", "TLT", "LQD", "SHV"]
NAMES = {
    "SPY": "S&P 500", "IWM": "Russell 2000 (small cap)",
    "TLT": "20+ year Treasuries", "LQD": "Investment-grade credit",
    "SHV": "Short Treasuries (cash-like)",
}
TRADING_DAYS = 252

parser = argparse.ArgumentParser(description="Solve the allocation across risk preferences.")
parser.add_argument("--start", default="2012-01-01", help="YYYY-MM-DD")
parser.add_argument("--end", default=str(date.today()), help="YYYY-MM-DD (default: today)")
parser.add_argument(
    "--tickers", default=",".join(TICKERS),
    help="Comma-separated. The last one is treated as the cash-like leg.",
)
args = parser.parse_args()
TICKERS = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
CASH = TICKERS[-1]

raw = yf.download(TICKERS, start=args.start, end=args.end,
                  progress=False, auto_adjust=True)
closes = raw["Close"][TICKERS].dropna()
returns = closes.pct_change().dropna()

mu = returns.mean() * TRADING_DAYS
cov = returns.cov() * TRADING_DAYS
# The last ticker is the cash-like leg, so it stands in for the risk-free rate.
rf = float(mu[CASH])

def stats(w: np.ndarray) -> tuple[float, float, float]:
    r = float(w @ mu)
    v = float(np.sqrt(w @ cov @ w))
    return r, v, (r - rf) / v if v > 0 else 0.0

CONSTRAINTS = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
BOUNDS = tuple((0.0, 1.0) for _ in TICKERS)
START = np.full(len(TICKERS), 1 / len(TICKERS))

def solve(objective) -> np.ndarray:
    res = minimize(objective, START, method="SLSQP",
                   bounds=BOUNDS, constraints=CONSTRAINTS)
    return res.x

# The notebook's sweep: the objective blends minimising variance with
# maximising Sharpe, and the weight on the Sharpe term is swept. At 0 it is a
# pure minimum-variance portfolio; as it grows the solution chases return.
SHARPE_WEIGHTS = [0, 0.0001, 0.0002, 0.0004, 0.0005, 0.001, 0.002, 0.005,
                  0.01, 0.05, 0.5, 1]

sweep = []
for sw in SHARPE_WEIGHTS:
    def objective(w, sw=sw):
        r, v, s = stats(w)
        return v**2 - sw * s
    w = solve(objective)
    r, v, s = stats(w)
    sweep.append({
        "sharpe_weight": sw,
        "weights": {t: round(float(x), 4) for t, x in zip(TICKERS, w)},
        "return": round(r, 4), "volatility": round(v, 4), "sharpe": round(s, 3),
    })
    print(f"  sharpe_w={sw:<7} ret={r:+.2%} vol={v:.2%} sharpe={s:.2f}  "
          f"{ {t: f'{x:.0%}' for t, x in zip(TICKERS, w) if x > 0.01} }")

# Efficient frontier: minimum variance at each achievable target return.
lo, hi = float(mu.min()), float(mu.max())
frontier = []
for target in np.linspace(lo, hi, 40):
    cons = CONSTRAINTS + ({"type": "eq", "fun": lambda w, t=target: w @ mu - t},)
    res = minimize(lambda w: w @ cov @ w, START, method="SLSQP",
                   bounds=BOUNDS, constraints=cons)
    if res.success:
        r, v, s = stats(res.x)
        frontier.append({
            "return": round(r, 4), "volatility": round(v, 4), "sharpe": round(s, 3),
            "weights": {t: round(float(x), 4) for t, x in zip(TICKERS, res.x)},
        })

# NAV paths for the notable allocations, so the trade-off is visible over time.
def nav(weights: dict[str, float]) -> list[float]:
    w = np.array([weights[t] for t in TICKERS])
    port = (returns[TICKERS] @ w)
    return [round(float(v), 2) for v in 100 * (1 + port).cumprod()]

max_sharpe = max(frontier, key=lambda f: f["sharpe"])
min_vol = min(frontier, key=lambda f: f["volatility"])
equal = {t: 1 / len(TICKERS) for t in TICKERS}

step = max(1, len(returns) // 400)
payload = {
    "generated": str(date.today()),
    "cash_leg": CASH,
    "growth_leg": TICKERS[0],
    "tickers": TICKERS,
    "names": NAMES,
    "start": str(closes.index[0].date()),
    "end": str(closes.index[-1].date()),
    "risk_free": round(rf, 4),
    "assets": [
        {
            "ticker": t, "name": NAMES[t],
            "return": round(float(mu[t]), 4),
            "volatility": round(float(np.sqrt(cov.loc[t, t])), 4),
            "sharpe": round((float(mu[t]) - rf) / float(np.sqrt(cov.loc[t, t])), 3),
        }
        for t in TICKERS
    ],
    "correlation": {
        a: {b: round(float(returns[a].corr(returns[b])), 3) for b in TICKERS}
        for a in TICKERS
    },
    "sweep": sweep,
    "frontier": frontier,
    "dates": [str(d.date()) for d in returns.index[::step]],
    "paths": {
        "Max Sharpe": nav(max_sharpe["weights"])[::step],
        "Min volatility": nav(min_vol["weights"])[::step],
        "Equal weight": nav(equal)[::step],
        f"100% {TICKERS[0]}": nav(
        {t: 1.0 if t == TICKERS[0] else 0.0 for t in TICKERS}
    )[::step],
    },
    "notable": {"max_sharpe": max_sharpe, "min_vol": min_vol},
}
path = OUT / "nb-stockbond.json"
path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
print(f"  nb-stockbond.json  {path.stat().st_size/1024:.1f} KB")
print(f"  max Sharpe {max_sharpe['sharpe']:.2f} at vol {max_sharpe['volatility']:.2%}")
