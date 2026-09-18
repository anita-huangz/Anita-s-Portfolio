"""Run the evaluation and print it. Reproduces every number in the README."""

from __future__ import annotations

import argparse
import sys

import pandas as pd

from .backtest import backtest_signal, buy_and_hold
from .baselines import ar_returns, drift, ewma, naive
from .data import load
from .leakage import measure_scaler_leak
from .metrics import diebold_mariano, directional_accuracy, return_r2, rmse
from .walkforward import rolling_origin, walk_forward

RULE = "-" * 76
SIGNALS = {
    "naive": naive,
    "drift": drift,
    "ewma_10": lambda c: ewma(c, span=10),
    "ar5_returns": lambda c: ar_returns(c, lags=5),
}


def _heading(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def single_split(close: pd.Series, start: str) -> None:
    _heading(f"ONE-STEP-AHEAD FORECASTS, {start} onward")
    test = close.loc[start:]
    previous = close.shift(1).loc[test.index]
    print(f"  {'forecast':<14}{'RMSE':>10}{'R2(returns)':>13}{'directional':>22}")
    for name, build in SIGNALS.items():
        forecast = build(close).loc[test.index]
        accuracy = directional_accuracy(test, forecast, previous)
        if accuracy.total:
            low, high = accuracy.interval()
            call = f"{accuracy.rate:.1%} [{low:.1%}, {high:.1%}]"
        else:
            call = "makes no call"
        print(
            f"  {name:<14}{rmse(test, forecast):>10,.0f}"
            f"{return_r2(test, forecast, previous):>13.4f}{call:>22}"
        )
    print("\n  A 95% interval that straddles 50% is a coin flip, however the")
    print("  point estimate reads. The naive forecast predicts no change, so it")
    print("  makes no directional call at all rather than getting them wrong.")


def leakage(close: pd.Series) -> None:
    _heading("THE SCALER LEAK — fitting MinMaxScaler before splitting")
    leak = measure_scaler_leak(close, train_fraction=0.8)
    print(f"  training data ends {leak.split_date.date()}, highest price seen "
          f"${leak.train_max:,.0f}")
    print(f"  highest price in the whole series                ${leak.full_max:,.0f}")
    print(f"  range the leaky scaler used is                   {leak.range_inflation:.2f}x wider")
    print(f"  share of that scale never reached in training    "
          f"{leak.unseen_high_fraction:.1%}")
    print("\n  MinMaxScaler divides by (max - min). Fitting it on the whole")
    print("  series tells the model, in the units it learns in, how high the")
    print("  price will eventually go.")


def walkforward_report(close: pd.Series, test_size: int) -> None:
    _heading("WALK-FORWARD — 21 rolling origins instead of one lucky split")
    folds = list(rolling_origin(pd.DatetimeIndex(close.index), test_size=test_size))
    print(f"  {len(folds)} origins, {folds[0].test_start.date()} to {folds[-1].test_end.date()}\n")
    print(f"  {'forecast':<14}{'mean RMSE':>11}{'fold range':>22}{'mean R2':>10}"
          f"{'folds R2>0':>12}")
    for name, build in SIGNALS.items():
        result = walk_forward(close, build, name, test_size=test_size)
        low, high = result.rmse_spread
        span = f"${low:,.0f} - ${high:,.0f}"
        print(
            f"  {name:<14}{result.mean_rmse:>11,.0f}{span:>22}"
            f"{result.mean_return_r2:>10.4f}"
            f"{f'{result.folds_beating_zero_r2}/{len(result.folds)}':>12}"
        )
    print("\n  The same method scores single digits in an early fold and")
    print("  thousands in a late one. RMSE on a price level is a statement")
    print("  about the price level, not about the forecast.")


def trading(close: pd.Series, start: str) -> None:
    _heading("DOES IT MAKE MONEY? — the only question that settles it")
    recent = close.loc[start:]
    held = buy_and_hold(recent)
    print(f"  {'signal':<14}{'0 bps':>10}{'10 bps':>10}{'30 bps':>10}"
          f"{'trades':>9}{'in mkt':>8}")
    for name, build in SIGNALS.items():
        signal = build(close).loc[recent.index]
        runs = [backtest_signal(recent, signal, cost_bps=b) for b in (0, 10, 30)]
        print(
            f"  {name:<14}" + "".join(f"{r.total_return:>+10.1%}" for r in runs)
            + f"{runs[0].trades:>9}{runs[0].time_in_market:>8.0%}"
        )
    print(f"  {'buy & hold':<14}{held.total_return:>+10.1%}{'':>20}"
          f"{held.trades:>9}{held.time_in_market:>8.0%}")
    print(f"\n  Buy and hold: Sharpe {held.sharpe:+.2f}, max drawdown "
          f"{held.max_drawdown:.1%}.")
    print("  Nothing here beats it, and 30 bps of cost removes most of what")
    print("  the apparent edge was worth. The drift signal is long every day,")
    print("  so its directional accuracy is not timing anything.")


def lstm_report(close: pd.Series) -> None:
    _heading("THE SAVED LSTM — against the one-line baseline")
    from . import lstm

    if not lstm.available():
        print("  TensorFlow or the saved model is unavailable; skipping.")
        return

    honest = lstm.predict(close, leaky=False)
    leaky = lstm.predict(close, leaky=True)
    test = close.loc[honest.index]
    previous = close.shift(1).loc[honest.index]
    reference = naive(close).loc[honest.index]

    print(f"  {'forecast':<16}{'RMSE':>10}{'R2(returns)':>14}{'directional':>20}")
    for name, forecast in [
        ("LSTM (honest)", honest),
        ("LSTM (as written)", leaky),
        ("naive", reference),
    ]:
        accuracy = directional_accuracy(test, forecast, previous)
        call = (
            f"{accuracy.rate:.1%} [{accuracy.interval()[0]:.0%}, "
            f"{accuracy.interval()[1]:.0%}]"
            if accuracy.total
            else "makes no call"
        )
        print(
            f"  {name:<16}{rmse(test, forecast):>10,.0f}"
            f"{return_r2(test, forecast, previous):>14.2f}{call:>20}"
        )

    test_result = diebold_mariano(
        test.to_numpy(), honest.to_numpy(), reference.to_numpy()
    )
    print(f"\n  Diebold-Mariano, LSTM against naive: DM = {test_result.statistic:+.2f}, "
          f"p = {test_result.p_value:.1e}")
    print(f"  -> the better forecast is the {test_result.better}.")
    print("\n  That is the ratio turned into a hypothesis test. The leak makes")
    print(f"  the model look {rmse(test, honest) / rmse(test, leaky):.2f}x better than it is.")
    print("  It is not walk-forward evaluated -- retraining at 21 origins is")
    print("  hours of compute -- which if anything flatters it.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None, help="Daily bars (default: bundled).")
    parser.add_argument("--from", dest="start", default="2023-01-01")
    parser.add_argument("--test-size", type=int, default=180)
    parser.add_argument(
        "--section",
        choices=["all", "split", "leakage", "walkforward", "trading", "lstm"],
        default="all",
    )
    args = parser.parse_args(argv)

    try:
        prices = load(args.csv) if args.csv else load()
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    close = prices.close
    print(f"{len(prices):,} daily bars, {prices.dates.min().date()} to "
          f"{prices.dates.max().date()}")

    want = args.section
    if want in {"all", "split"}:
        single_split(close, args.start)
    if want in {"all", "leakage"}:
        leakage(close)
    if want in {"all", "walkforward"}:
        walkforward_report(close, args.test_size)
    if want in {"all", "trading"}:
        trading(close, args.start)
    if want in {"all", "lstm"}:
        lstm_report(close)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
