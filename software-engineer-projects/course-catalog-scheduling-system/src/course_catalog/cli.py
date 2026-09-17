"""Command-line search over the catalog."""

from __future__ import annotations

import argparse
import sys

from .catalog import Catalog, build_schedule
from .meeting import Day


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search a course catalog and check for schedule conflicts."
    )
    parser.add_argument("--csv", default=None, help="Catalog CSV (default: bundled).")
    parser.add_argument("--code", help="Match courses whose code starts with this.")
    parser.add_argument("--keyword", help="Match course title or instructor.")
    parser.add_argument("--day", help="Match courses meeting on this day.")
    parser.add_argument(
        "--schedule",
        default="",
        help="Comma-separated codes you are already enrolled in; conflicts are excluded.",
    )
    parser.add_argument(
        "--free", action="store_true", help="List everything that fits your schedule."
    )
    args = parser.parse_args(argv)

    try:
        catalog = Catalog.from_csv(args.csv) if args.csv else Catalog.bundled()
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    enrolled = [c.strip() for c in args.schedule.split(",") if c.strip()]
    try:
        schedule = build_schedule(catalog, enrolled)
    except (KeyError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if schedule:
        print(f"Enrolled ({len(schedule)}):")
        for course in schedule:
            print(f"  {course}")
        print()

    results: list = []
    label = ""
    if args.code:
        results, label = catalog.by_code(args.code, schedule or None), f"code ~ {args.code!r}"
    elif args.keyword:
        results, label = (
            catalog.by_keyword(args.keyword, schedule or None),
            f"keyword ~ {args.keyword!r}",
        )
    elif args.day:
        try:
            day = Day.parse(args.day)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
        results, label = catalog.by_day(day, schedule or None), f"meets {day.name.title()}"
    elif args.free:
        results, label = catalog.without_conflicts(schedule), "fits your schedule"
    else:
        results, label = list(catalog), "all courses"

    print(f"{len(results)} course(s) — {label}:")
    for course in results:
        print(f"  {course}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
