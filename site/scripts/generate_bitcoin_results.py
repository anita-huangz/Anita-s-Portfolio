"""Bitcoin: walk-forward baselines, the LSTM against them, and a trading test.

The previous version ran the saved LSTM on one 20% tail, reported RMSE and a
directional-accuracy percentage, and left the reader to judge whether either
number was good. Both questions the project now answers were missing: is the
model better than "tomorrow equals today" by more than noise, and does any of
it survive being traded?

So this imports `btc_forecast` and emits what the package computes -- rolling
origins rather than one split, a Diebold-Mariano test rather than a comparison
of two point estimates, Wilson intervals on the directional hit rate, and a
cost-aware backtest against buy-and-hold. The LSTM is still here; it is now one
forecaster among several rather than the subject.
"""
from __future__ import annotations
import argparse, json, os, pathlib, sys, warnings
from datetime import date
warnings.filterwarnings("ignore"); os.environ["TF_CPP_MIN_LOG_LEVEL"] = "3"
import numpy as np, pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
PROJECT = ROOT / "inference/bitcoin-and-asset-trading"
sys.path.insert(0, str(PROJECT / "src"))

from btc_forecast import lstm
from btc_forecast.backtest import backtest_signal, buy_and_hold
from btc_forecast.baselines import ar_returns, drift, ewma, naive
from btc_forecast.data import load
from btc_forecast.leakage import measure_scaler_leak
from btc_forecast.metrics import (
    diebold_mariano,
    directional_accuracy,
    mae,
    mape,
    return_r2,
    rmse,
)
from btc_forecast.walkforward import walk_forward

OUT = ROOT / "site/src/data/demos"


def maybe(value: float, places: int = 4) -> float | None:
    """`null` rather than NaN, which is not valid JSON.

    Not a formatting detail. The naive forecast abstains on every day -- it
    predicts no move, so it makes no directional call -- and its hit rate is
    genuinely undefined rather than zero or fifty percent. The chart has to be
    able to say "no call" instead of drawing a bar.
    """
    return None if value is None or not np.isfinite(value) else round(float(value), places)

parser = argparse.ArgumentParser(description="Walk-forward evaluation of BTC forecasters.")
parser.add_argument("--train-fraction", type=float, default=0.8,
                    help="Single-split boundary, for the LSTM comparison.")
parser.add_argument("--min-train", type=int, default=1000, help="Walk-forward warm-up")
parser.add_argument("--test-size", type=int, default=180, help="Days per rolling fold")
parser.add_argument("--cost-bps", type=float, default=10.0, help="One-way trading cost")
parser.add_argument("--no-extend", action="store_true",
                    help="Skip topping the archive up with recent prices from Yahoo.")
parser.add_argument("--no-lstm", action="store_true", help="Skip the TensorFlow model.")
args = parser.parse_args()

prices = load()
close = prices.close
print(f"  {len(close):,} daily bars "
      f"({close.index[0].date()} to {close.index[-1].date()})")

if not args.no_extend:
    # The packaged CSV stops whenever it was last rebuilt. Topping it up from
    # Yahoo keeps the evaluation window current instead of frozen months back.
    import yfinance as yf

    resume = close.index[-1] + pd.Timedelta(days=1)
    if resume.date() < date.today():
        recent = yf.download("BTC-USD", start=str(resume.date()),
                             end=str(date.today()), progress=False, auto_adjust=True)
        if recent is not None and not recent.empty:
            extra = recent["Close"]
            if isinstance(extra, pd.DataFrame):
                extra = extra.iloc[:, 0]
            extra.index = pd.to_datetime(extra.index).tz_localize(None)
            before = len(close)
            close = pd.concat([close, extra.astype(float)])
            close = close[~close.index.duplicated(keep="first")].sort_index()
            close.name = "Close"
            print(f"  extended with Yahoo: +{len(close) - before} days "
                  f"-> {close.index[-1].date()}")

# ---------------------------------------------------------------------------
# Walk-forward: every baseline scored on every rolling origin.
# ---------------------------------------------------------------------------
FORECASTERS = {
    "naive (t-1)": naive,
    "drift": drift,
    "EWMA(10)": ewma,
    "AR(5) on returns": ar_returns,
}

walk = []
for name, fn in FORECASTERS.items():
    result = walk_forward(close, fn, name,
                          min_train=args.min_train, test_size=args.test_size)
    acc = result.pooled_accuracy
    low, high = acc.interval()
    lo_rmse, hi_rmse = result.rmse_spread
    walk.append({
        "name": name,
        "folds": len(result.folds),
        "mean_rmse": round(result.mean_rmse, 2),
        "rmse_low": round(lo_rmse, 2),
        "rmse_high": round(hi_rmse, 2),
        "mean_return_r2": round(result.mean_return_r2, 5),
        "folds_beating_zero_r2": result.folds_beating_zero_r2,
        "direction": {
            "rate": maybe(acc.rate),
            "low": maybe(low),
            "high": maybe(high),
            "correct": acc.correct,
            "total": acc.total,
            "abstained": acc.abstained,
            "abstention_rate": maybe(acc.abstention_rate),
            "beats_coin_flip": acc.beats_coin_flip,
        },
        "per_fold": [
            {
                "fold": f.fold.index,
                "test_start": str(f.fold.test_start.date()),
                "test_end": str(f.fold.test_end.date()),
                "rmse": round(f.rmse, 2),
                "return_r2": round(f.return_r2, 5),
                "direction": maybe(f.accuracy.rate),
            }
            for f in result.folds
        ],
    })
    print(f"  {name:<18} RMSE {result.mean_rmse:9,.0f} "
          f"[{lo_rmse:,.0f}-{hi_rmse:,.0f}]  return R2 {result.mean_return_r2:+.4f}  "
          f"direction {acc.rate:.1%} (abstained {acc.abstention_rate:.0%})  "
          f"{result.folds_beating_zero_r2}/{len(result.folds)} folds beat R2=0")

# ---------------------------------------------------------------------------
# Single split: the LSTM against naive on identical days.
# ---------------------------------------------------------------------------
split = int(len(close) * args.train_fraction)
test_index = close.index[split:]
baseline = naive(close).reindex(test_index)
previous = close.shift(1).reindex(test_index)
actual = close.reindex(test_index)

leak = measure_scaler_leak(close, train_fraction=args.train_fraction)
single = {}
comparison = None
series: list[dict] = []

if args.no_lstm or not lstm.available():
    print("  LSTM skipped (TensorFlow or the saved model is unavailable)")
else:
    honest = lstm.predict(close, train_fraction=args.train_fraction, leaky=False)
    leaky = lstm.predict(close, train_fraction=args.train_fraction, leaky=True)
    common = honest.index.intersection(test_index)
    a = actual.reindex(common)
    p = previous.reindex(common)
    n = baseline.reindex(common)
    h = honest.reindex(common)
    k = leaky.reindex(common)

    def describe(forecast: pd.Series) -> dict:
        acc = directional_accuracy(a, forecast, p)
        low, high = acc.interval()
        return {
            "rmse": round(rmse(a.to_numpy(), forecast.to_numpy()), 2),
            "mae": round(mae(a.to_numpy(), forecast.to_numpy()), 2),
            "mape": round(mape(a.to_numpy(), forecast.to_numpy()), 3),
            "return_r2": round(return_r2(a, forecast, p), 5),
            "direction": maybe(acc.rate),
            "direction_low": maybe(low),
            "direction_high": maybe(high),
            "abstention_rate": maybe(acc.abstention_rate),
            "beats_coin_flip": acc.beats_coin_flip,
        }

    single = {
        "days": len(common),
        "first": str(common[0].date()),
        "last": str(common[-1].date()),
        "naive (t-1)": describe(n),
        "LSTM (honest scaling)": describe(h),
        "LSTM (leaky scaling)": describe(k),
    }

    # Is the LSTM's RMSE edge over naive bigger than the noise in the loss
    # difference? A point estimate cannot answer that; this can.
    dm = diebold_mariano(a.to_numpy(), h.to_numpy(), n.to_numpy())
    comparison = {
        "statistic": round(dm.statistic, 3),
        "p": round(dm.p_value, 4),
        "mean_loss_difference": round(dm.mean_loss_difference, 2),
        "observations": dm.observations,
        "lag": dm.lag,
        "significant": dm.significant,
        "better": dm.better,
    }
    print(f"  Diebold-Mariano LSTM vs naive: t={dm.statistic:+.2f} "
          f"p={dm.p_value:.3f} -> {dm.better}")

    step = max(1, len(common) // 400)
    series = [
        {
            "date": str(d.date()),
            "actual": round(float(av), 2),
            "naive": round(float(nv), 2),
            "lstm": round(float(hv), 2),
            "leaky": round(float(kv), 2),
        }
        for d, av, nv, hv, kv in list(
            zip(common, a, n, h, k, strict=True)
        )[::step]
    ]

# ---------------------------------------------------------------------------
# Trading: does any of the above survive costs?
# ---------------------------------------------------------------------------
hold = buy_and_hold(close.loc[test_index])
strategies = [{
    "name": "buy and hold",
    "total_return": round(hold.total_return, 4),
    "annualised": round(hold.annualised_return, 4),
    "volatility": round(hold.volatility, 4),
    "sharpe": round(hold.sharpe, 3),
    "max_drawdown": round(hold.max_drawdown, 4),
    "trades": hold.trades,
    "time_in_market": round(hold.time_in_market, 4),
}]
signals = {name: fn(close).reindex(test_index) for name, fn in FORECASTERS.items()}
if single:
    signals["LSTM (honest scaling)"] = lstm.predict(
        close, train_fraction=args.train_fraction, leaky=False
    ).reindex(test_index)
for name, forecast in signals.items():
    usable = forecast.dropna()
    if usable.empty:
        continue
    bt = backtest_signal(close.loc[usable.index], usable, cost_bps=args.cost_bps)
    strategies.append({
        "name": name,
        "total_return": round(bt.total_return, 4),
        "annualised": round(bt.annualised_return, 4),
        "volatility": round(bt.volatility, 4),
        "sharpe": round(bt.sharpe, 3),
        "max_drawdown": round(bt.max_drawdown, 4),
        "trades": bt.trades,
        "time_in_market": round(bt.time_in_market, 4),
    })
    print(f"  trade {name:<22} return {bt.total_return:+7.1%}  "
          f"Sharpe {bt.sharpe:5.2f}  {bt.trades} trades"
          + ("  [never takes a position]" if bt.trades == 0 else ""))
print(f"  trade {'buy and hold':<22} return {hold.total_return:+7.1%}  "
      f"Sharpe {hold.sharpe:5.2f}")

payload = {
    "generated": str(date.today()),
    "source": (
        "Kaggle: mczielinski/bitcoin-historical-data (minute trades resampled to "
        "daily bars and committed with the package), topped up with Yahoo Finance "
        "BTC-USD daily closes"
    ),
    "source_url": "https://www.kaggle.com/datasets/mczielinski/bitcoin-historical-data",
    "bars": len(close),
    "first_date": str(close.index[0].date()),
    "last_date": str(close.index[-1].date()),
    "settings": {
        "train_fraction": args.train_fraction,
        "min_train": args.min_train,
        "test_size": args.test_size,
        "cost_bps": args.cost_bps,
    },
    "model": "2-layer LSTM (100, 50) with dropout, dense 25 -> 1; 72,301 parameters",
    "lookback": lstm.LOOKBACK,
    "walk_forward": walk,
    "single_split": single,
    "diebold_mariano": comparison,
    "scaler_leak": {
        "train_max": round(leak.train_max, 2),
        "train_min": round(leak.train_min, 2),
        "full_max": round(leak.full_max, 2),
        "full_min": round(leak.full_min, 2),
        "split_date": str(leak.split_date.date()),
        "range_inflation": round(leak.range_inflation, 3),
        "unseen_high_fraction": round(leak.unseen_high_fraction, 4),
    },
    "strategies": strategies,
    "series": series,
}
path = OUT / "nb-bitcoin.json"
path.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
print(f"  nb-bitcoin.json  {path.stat().st_size/1024:.1f} KB")
