"""Command-line entry point."""

from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta

from .factors import FACTOR_REGISTRY, get_factors
from .metrics import format_metrics, performance_metrics
from .simulation import run_backtest

SNAPSHOT_FACTORS = {"value", "size"}

#: Momentum needs 252 trading days before it can rank anything, so the
#: default window has to be comfortably longer than one year.
YEARS_OF_HISTORY = 4


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Backtest a cross-sectional factor strategy with point-in-time exposures."
    )
    parser.add_argument(
        "--tickers", default="AAPL,MSFT,GOOGL,AMZN,META,NVDA,AVGO,ORCL"
    )
    # Relative to today rather than pinned, so the default window keeps
    # moving instead of silently ageing into a historical backtest.
    today = date.today()
    parser.add_argument(
        "--start",
        default=str(today - timedelta(days=YEARS_OF_HISTORY * 365)),
        help="YYYY-MM-DD (default: %(default)s)",
    )
    parser.add_argument(
        "--end", default=str(today), help="YYYY-MM-DD (default: today)"
    )
    parser.add_argument("--cash", type=float, default=100_000.0)
    parser.add_argument(
        "--factors",
        default="momentum,low_volatility",
        help=f"Comma-separated. Available: {','.join(sorted(FACTOR_REGISTRY))}",
    )
    parser.add_argument("--top-n", type=int, default=3)
    parser.add_argument("--scheme", choices=["equal", "rank"], default="equal")
    parser.add_argument("--rebalance-every", type=int, default=21)
    parser.add_argument("--cost-bps", type=float, default=0.0)
    parser.add_argument("--attribution", action="store_true")
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args(argv)

    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    names = [f.strip() for f in args.factors.split(",") if f.strip()]

    try:
        factors = get_factors(names)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    needs_snapshot = SNAPSHOT_FACTORS & set(names)
    if needs_snapshot:
        print(
            f"warning: {sorted(needs_snapshot)} use a present-day fundamentals "
            "snapshot applied to historical rebalances, which is look-ahead bias. "
            "Price-only factors (momentum, low_volatility) are point-in-time.",
            file=sys.stderr,
        )

    from .data import download_prices, fetch_fundamentals

    try:
        prices = download_prices(tickers, args.start, args.end)
        static = fetch_fundamentals(tickers) if needs_snapshot else None
    except Exception as exc:
        print(f"error: failed to load market data: {exc}", file=sys.stderr)
        return 1

    result = run_backtest(
        prices=prices,
        factors=factors,
        initial_cash=args.cash,
        rebalance_every=args.rebalance_every,
        top_n=args.top_n,
        scheme=args.scheme,
        cost_bps=args.cost_bps,
        static_exposures=static,
    )

    print(f"\n{' + '.join(names)} | top {args.top_n} | {args.scheme}-weighted")
    print(f"{len(result.rebalance_dates)} rebalances, ${result.total_costs:,.2f} in costs")
    if result.skipped_rebalances:
        print(f"{result.skipped_rebalances} rebalances skipped (no scorable names)")
    print()
    print(format_metrics(performance_metrics(result.nav)))

    if args.attribution:
        from .attribution import attribute
        from .data import load_fama_french

        try:
            print("\nFama-French 3-factor attribution:")
            print(attribute(result.nav, load_fama_french()).render())
        except Exception as exc:
            print(f"  attribution unavailable: {exc}", file=sys.stderr)

    if args.plot:
        from .plotting import plot_drawdown, plot_nav

        plot_nav(result.nav, show=False)
        plot_drawdown(result.nav)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
