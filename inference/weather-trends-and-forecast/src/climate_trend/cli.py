"""Run the analysis and print it. Reproduces every number in the README."""

from __future__ import annotations

import argparse
import sys

from .data import load
from .trend import (
    block_bootstrap,
    mann_kendall,
    newey_west,
    ordinary_least_squares,
    residual_autocorrelation,
)

RULE = "-" * 78


def _heading(text: str) -> None:
    print(f"\n{text}\n{RULE}")


def warming(cities) -> None:
    _heading("WARMING RATE, DEGREES C PER DECADE")
    print(f"  {'city':<12}{'Sen slope':>11}{'95% interval':>22}"
          f"{'yr-to-yr sd':>13}{'decades to notice':>19}")
    for name, series in sorted(
        cities.items(), key=lambda kv: -mann_kendall(kv[1]).slope
    ):
        trend = mann_kendall(series)
        # How many decades of warming before it exceeds one year's wobble.
        decades = series.year_to_year_sd / trend.slope if trend.slope > 0 else float("inf")
        interval = f"[{trend.low:+.3f}, {trend.high:+.3f}]"
        print(
            f"  {name:<12}{trend.slope:>+11.3f}{interval:>22}"
            f"{series.year_to_year_sd:>13.2f}{decades:>19.1f}"
        )
    print("\n  Every city is warming, and every interval excludes zero. The last")
    print("  column is why nobody notices: a decade of trend is smaller than one")
    print("  year's natural variation everywhere on this list.")


def uncertainty(cities, city: str, draws: int) -> None:
    _heading(f"THE ERROR BAR — {city}")
    series = cities[city]
    print(f"  {len(series)} annual means, {series.span[0]}-{series.span[1]}\n")
    print(f"  {'method':<22}{'slope':>8}{'std err':>9}   {'95% interval':<22}{'p':>10}")
    for trend in (
        ordinary_least_squares(series),
        newey_west(series),
        block_bootstrap(series, draws=draws),
        mann_kendall(series),
    ):
        print("  " + trend.row())

    auto = residual_autocorrelation(series)
    print(f"\n  residual lag-1 correlation {auto.lag1:+.3f} (p={auto.lag1_p_value:.4f})")
    print(f"  Durbin-Watson {auto.durbin_watson:.2f}")
    print(f"  effective sample size {auto.effective_sample_size:.0f} of {auto.n} years")
    print(f"  -> the OLS standard error is too small by about "
          f"{(auto.inflation - 1) * 100:.0f}%")
    print("\n  A warm year follows a warm year, so the residuals are not")
    print("  independent and OLS's error bar is too narrow. Newey-West corrects")
    print("  it; the block bootstrap gets there without assuming a model of the")
    print("  correlation; Sen's slope assumes nothing about the distribution at")
    print("  all. All four agree on the slope. Only OLS disagrees on the width.")


def autocorrelation_table(cities) -> None:
    _heading("WHY THE TEXTBOOK ERROR BAR IS WRONG EVERYWHERE HERE")
    print(f"  {'city':<12}{'lag-1':>8}{'p':>9}{'Durbin-Watson':>16}"
          f"{'effective n':>14}{'SE understated':>17}")
    for name, series in cities.items():
        auto = residual_autocorrelation(series)
        print(
            f"  {name:<12}{auto.lag1:>+8.3f}{auto.lag1_p_value:>9.4f}"
            f"{auto.durbin_watson:>16.2f}"
            f"{f'{auto.effective_sample_size:.0f}/{auto.n}':>14}"
            f"{(auto.inflation - 1) * 100:>16.0f}%"
        )
    print("\n  Significant in all six. Tokyo's 75 years are worth about 32")
    print("  independent ones, so its naive interval is half the width it")
    print("  should be.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--csv", default=None)
    parser.add_argument("--city", default="London")
    parser.add_argument("--draws", type=int, default=2000)
    parser.add_argument(
        "--section",
        choices=["all", "warming", "uncertainty", "autocorrelation"],
        default="all",
    )
    args = parser.parse_args(argv)

    try:
        cities = load(args.csv) if args.csv else load()
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.city not in cities:
        print(f"error: no city {args.city!r}; have {sorted(cities)}", file=sys.stderr)
        return 2

    print(f"{len(cities)} cities, annual mean temperature from ERA5 reanalysis")
    if args.section in {"all", "warming"}:
        warming(cities)
    if args.section in {"all", "uncertainty"}:
        uncertainty(cities, args.city, args.draws)
    if args.section in {"all", "autocorrelation"}:
        autocorrelation_table(cities)
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
