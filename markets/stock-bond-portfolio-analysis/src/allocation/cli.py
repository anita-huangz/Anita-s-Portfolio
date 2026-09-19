"""Run the backtests and print them. Reproduces every number in the README."""

from __future__ import annotations

import argparse
import sys

from .backtest import in_sample_result, rolling_backtest, weight_instability
from .data import DESCRIPTIONS, load
from .estimate import ledoit_wolf
from .optimise import ALLOCATORS

RULE = "-" * 78
HEADER = (
    f"  {'strategy':<22}{'ann ret':>9}{'vol':>9}{'Sharpe':>8}"
    f"{'maxDD':>10}{'turnover':>11}{'cost':>9}"
)


def _heading(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def universe(prices) -> None:
    _heading("THE UNIVERSE")
    summary = prices.annualised_summary()
    print(f"  {'ticker':<8}{'return':>9}{'vol':>9}{'Sharpe':>8}   what it is")
    for ticker, row in summary.iterrows():
        print(
            f"  {ticker:<8}{row['annual_return']:>+9.2%}{row['annual_vol']:>9.2%}"
            f"{row['sharpe']:>8.2f}   {DESCRIPTIONS.get(ticker, '')}"
        )
    _, intensity = ledoit_wolf(prices.returns)
    print(f"\n  Ledoit-Wolf shrinkage intensity on the full sample: {intensity:.4f}")
    print("  (Low, because 4,200 days is a lot of data for five assets. It rises")
    print("   sharply on the two-year estimation windows the backtest uses.)")


def out_of_sample(returns, lookback: int, cadence: int, cost_bps: float) -> None:
    _heading(
        f"OUT OF SAMPLE — {lookback}-day window, rebalanced every {cadence} days, "
        f"{cost_bps:.0f} bps"
    )
    print(HEADER)
    results = {}
    for name, allocate in ALLOCATORS.items():
        result = rolling_backtest(
            returns, allocate, name,
            lookback=lookback, rebalance_every=cadence, cost_bps=cost_bps,
        )
        results[name] = result
        print("  " + result.row())

    naive = results["equal weight (1/N)"]
    print("\n  1/N earns the most, and it is the rule that estimates nothing.")
    print("  Maximum Sharpe -- the only rule that needs expected returns --")
    print("  comes last on the Sharpe ratio it optimises.")
    print("\n  weight instability (mean |change| per rebalance):")
    for name, result in results.items():
        print(f"    {name:<22}{weight_instability(result):.4f}")
    print("\n  Minimum variance's Sharpe is an artefact: it holds "
          f"{naive.weights.columns[-1]} at "
          f"{results['minimum variance'].weights['SHV'].mean():.0%} and so has")
    print("  almost no volatility to divide by. Read its return instead.")


def in_sample(returns) -> None:
    _heading("IN SAMPLE — what the original notebook reported")
    print(HEADER)
    for name, allocate in ALLOCATORS.items():
        print("  " + in_sample_result(returns, allocate, name).row())
    print("\n  Optimised on the whole history, then scored on the same history.")
    print("  Maximum Sharpe reports a Sharpe above 5 here and 0.32 out of")
    print("  sample. 1/N barely moves, because it has no parameters to overfit.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--lookback", type=int, default=504)
    parser.add_argument("--rebalance-every", type=int, default=63)
    parser.add_argument("--cost-bps", type=float, default=5.0)
    parser.add_argument(
        "--section",
        choices=["all", "universe", "out", "in"],
        default="all",
    )
    args = parser.parse_args(argv)

    try:
        prices = load(args.csv) if args.csv else load()
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(prices):,} trading days, {prices.frame.index.min().date()} to "
          f"{prices.frame.index.max().date()}")
    if args.section in {"all", "universe"}:
        universe(prices)
    if args.section in {"all", "out"}:
        out_of_sample(
            prices.returns, args.lookback, args.rebalance_every, args.cost_bps
        )
    if args.section in {"all", "in"}:
        in_sample(prices.returns)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
