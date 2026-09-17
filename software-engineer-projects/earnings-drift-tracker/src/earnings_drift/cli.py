"""Command-line entry point."""

from __future__ import annotations

import argparse
import logging
import sys

from .drift import analyze_drift
from .models import Stock
from .report import format_summary, plot_drift
from .sources import MissingAPIKey, load_earnings, load_price_data


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Measure post-earnings-announcement drift against analyst surprise."
    )
    parser.add_argument("ticker", nargs="?", default="AAPL")
    parser.add_argument("--start", default="2021-01-01")
    parser.add_argument("--end", default="2023-12-31")
    parser.add_argument("--limit", type=int, default=12, help="Earnings reports to fetch.")
    parser.add_argument("--horizons", default="1,5,10")
    parser.add_argument("--plot", action="store_true")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s"
    )
    horizons = tuple(int(h) for h in args.horizons.split(",") if h.strip())

    stock = Stock(args.ticker.upper())
    try:
        stock.set_price_data(load_price_data(stock.ticker, args.start, args.end))
        for report in load_earnings(stock.ticker, limit=args.limit):
            stock.add_earnings(report)
    except MissingAPIKey as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"error: failed to load data: {exc}", file=sys.stderr)
        return 1

    drift = analyze_drift(stock, horizons)
    print(format_summary(drift, horizons))

    if args.plot and not drift.empty:
        plot_drift(drift, horizons)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
