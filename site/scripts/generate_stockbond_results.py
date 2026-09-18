"""Stock-bond: the out-of-sample comparison, not the in-sample optimisation.

The previous version swept a risk preference through a constrained optimiser
and drew an efficient frontier. Both are fitted on the whole history and scored
on the same history, which is the mistake the `allocation` package exists to
measure: the frontier is a picture of the estimation error, and the "max Sharpe"
point on it is the one that overfit hardest.

So the frontier stays -- it is what the notebook produced and people expect to
see -- but it is now drawn beside the rolling out-of-sample backtest of the same
rules, with the in-sample number next to the realised one for each. Prices are
fetched live so the window runs to today; every statistic comes from the package.
"""
from __future__ import annotations
import argparse, json, pathlib, sys, warnings
from datetime import date
import numpy as np, pandas as pd, yfinance as yf
from scipy.optimize import minimize
warnings.filterwarnings("ignore")

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "data-science-projects/stock-bond-portfolio-analysis/src"))

from allocation.backtest import (
    in_sample_result,
    rolling_backtest,
    weight_instability,
)
from allocation.data import DESCRIPTIONS, TRADING_DAYS, Prices
from allocation.estimate import expected_returns, ledoit_wolf, sample_covariance
from allocation.optimise import ALLOCATORS

OUT = ROOT / "site/src/data/demos"
TICKERS = list(DESCRIPTIONS)

parser = argparse.ArgumentParser(description="Compare allocation rules in and out of sample.")
parser.add_argument("--start", default="2010-01-01", help="YYYY-MM-DD")
parser.add_argument("--end", default=str(date.today()), help="YYYY-MM-DD (default: today)")
parser.add_argument(
    "--tickers", default=",".join(TICKERS),
    help="Comma-separated. The last one is treated as the cash-like leg.",
)
parser.add_argument("--lookback", type=int, default=504, help="Estimation window, days")
parser.add_argument("--rebalance-every", type=int, default=63, help="Days between rebalances")
parser.add_argument("--cost-bps", type=float, default=10.0, help="One-way trading cost")
args = parser.parse_args()
TICKERS = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
CASH = TICKERS[-1]

raw = yf.download(TICKERS, start=args.start, end=args.end,
                  progress=False, auto_adjust=True)
closes = raw["Close"][TICKERS].dropna()
prices = Prices(frame=closes)
returns = prices.returns
# The cash-like leg stands in for the risk-free rate, as it does in the package.
rf = float(returns[CASH].mean() * TRADING_DAYS)

summary = prices.annualised_summary()
shrunk, intensity = ledoit_wolf(returns)
sample = sample_covariance(returns)

# ---------------------------------------------------------------------------
# What the notebook reported, and what the same rule actually earned.
# ---------------------------------------------------------------------------
def excess_sharpe(equity: pd.Series) -> float:
    """Sharpe against the cash leg rather than against zero.

    The package's own `sharpe` divides return by volatility with no risk-free
    subtraction, which is the standard convention there and fine for comparing
    two risky portfolios. It is misleading here: minimum variance puts ~100%
    into SHV, so its "Sharpe" is really cash's return-to-risk ratio and reads
    as a spectacular result. Subtracting the cash leg gives the number that
    answers "was taking any risk worth it", and for a cash portfolio it is
    approximately zero -- which is the correct answer.
    """
    daily = equity.pct_change().dropna()
    excess = (daily - returns[CASH].reindex(daily.index)).dropna()
    sd = excess.std(ddof=1)
    return float(excess.mean() / sd * np.sqrt(TRADING_DAYS)) if sd > 0 else 0.0


rules = []
backtests = {}
for name, allocator in ALLOCATORS.items():
    live = rolling_backtest(
        returns, allocator, name,
        lookback=args.lookback,
        rebalance_every=args.rebalance_every,
        cost_bps=args.cost_bps,
    )
    backtests[name] = live
    fitted = in_sample_result(returns, allocator, name)
    rules.append({
        "name": name,
        "in_sample": {
            "return": round(fitted.annualised_return, 4),
            "volatility": round(fitted.volatility, 4),
            "sharpe": round(fitted.sharpe, 3),
            "excess_sharpe": round(excess_sharpe(fitted.equity), 3),
            "max_drawdown": round(fitted.max_drawdown, 4),
        },
        "out_of_sample": {
            "return": round(live.annualised_return, 4),
            "volatility": round(live.volatility, 4),
            "sharpe": round(live.sharpe, 3),
            "excess_sharpe": round(excess_sharpe(live.equity), 3),
            "max_drawdown": round(live.max_drawdown, 4),
            "total_return": round(live.total_return, 4),
        },
        "sharpe_shortfall": round(
            excess_sharpe(fitted.equity) - excess_sharpe(live.equity), 3
        ),
        "average_turnover": round(live.average_turnover, 4),
        "cost_drag": round(live.cost_drag, 4),
        "weight_instability": round(weight_instability(live), 4),
        "rebalances": len(live.weights),
        "final_weights": {
            t: round(float(w), 4)
            for t, w in zip(returns.columns, live.weights.iloc[-1])
        },
        "weight_path": [
            {"date": str(pd.Timestamp(i).date()),
             **{t: round(float(row[t]), 4) for t in returns.columns}}
            for i, row in live.weights.iterrows()
        ],
    })
    print(f"  {name:<20} in-sample Sharpe {fitted.sharpe:5.2f} -> realised "
          f"{live.sharpe:5.2f}  (turnover {live.average_turnover:.1%}/rebal, "
          f"cost drag {live.cost_drag:.2%}/yr)\n{'':22}excess of cash: {excess_sharpe(fitted.equity):5.2f} -> {excess_sharpe(live.equity):5.2f}")

# Equity curves on the common out-of-sample window, so the panel compares
# like with like -- the backtests all start after the first lookback.
frame = pd.DataFrame({n: b.equity for n, b in backtests.items()}).dropna()
step = max(1, len(frame) // 400)

# ---------------------------------------------------------------------------
# The frontier: kept, labelled as in-sample, and with the out-of-sample points
# plotted on the same axes so the gap is a distance on the chart.
# ---------------------------------------------------------------------------
mu = expected_returns(returns)
cov = shrunk
bounds = tuple((0.0, 1.0) for _ in TICKERS)
budget = ({"type": "eq", "fun": lambda w: w.sum() - 1.0},)
start = np.full(len(TICKERS), 1 / len(TICKERS))

frontier = []
for target in np.linspace(float(mu.min()), float(mu.max()), 40):
    res = minimize(
        lambda w: w @ cov @ w, start, method="SLSQP", bounds=bounds,
        constraints=budget + ({"type": "eq", "fun": lambda w, t=target: w @ mu - t},),
    )
    if res.success:
        r = float(res.x @ mu)
        v = float(np.sqrt(res.x @ cov @ res.x))
        frontier.append({
            "return": round(r, 4), "volatility": round(v, 4),
            "sharpe": round((r - rf) / v, 3) if v > 0 else 0.0,
            "weights": {t: round(float(x), 4) for t, x in zip(TICKERS, res.x)},
        })

payload = {
    "generated": str(date.today()),
    "source": "Yahoo Finance daily adjusted closes",
    "source_url": "https://finance.yahoo.com/",
    "tickers": TICKERS,
    "names": DESCRIPTIONS,
    "cash_leg": CASH,
    "start": str(closes.index[0].date()),
    "end": str(closes.index[-1].date()),
    "days": len(returns),
    "risk_free": round(rf, 4),
    # `sharpe` is the package's return/volatility; `excess_sharpe` subtracts the
    # cash leg. Show the second when ranking rules -- see the note in the script.
    "sharpe_is_excess_of_zero": True,
    "settings": {
        "lookback": args.lookback,
        "rebalance_every": args.rebalance_every,
        "cost_bps": args.cost_bps,
    },
    "shrinkage_intensity": round(float(intensity), 4),
    "condition_number": {
        "sample": round(float(np.linalg.cond(sample)), 1),
        "shrunk": round(float(np.linalg.cond(shrunk)), 1),
    },
    "assets": [
        {
            "ticker": t, "name": DESCRIPTIONS.get(t, t),
            "return": round(float(summary.loc[t, "annual_return"]), 4),
            "volatility": round(float(summary.loc[t, "annual_vol"]), 4),
            "sharpe": round(float(summary.loc[t, "sharpe"]), 3),
        }
        for t in TICKERS
    ],
    "correlation": {
        a: {b: round(float(returns[a].corr(returns[b])), 3) for b in TICKERS}
        for a in TICKERS
    },
    "rules": rules,
    "frontier": frontier,
    "dates": [str(d.date()) for d in frame.index[::step]],
    "equity": {
        name: [round(float(v), 4) for v in frame[name].to_numpy()[::step]]
        for name in frame.columns
    },
}
path = OUT / "nb-stockbond.json"
path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
best_is = max(rules, key=lambda r: r["in_sample"]["sharpe"])
best_oos = max(rules, key=lambda r: r["out_of_sample"]["excess_sharpe"])
print(f"  best in-sample: {best_is['name']}  |  best realised: {best_oos['name']}")
print(f"  shrinkage intensity {intensity:.3f}; condition number "
      f"{np.linalg.cond(sample):.0f} -> {np.linalg.cond(shrunk):.0f}")
print(f"  nb-stockbond.json  {path.stat().st_size/1024:.1f} KB")
