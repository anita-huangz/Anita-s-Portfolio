"""Command-line search over the catalog."""

from __future__ import annotations

import argparse
import sys

from .catalog import Catalog, build_schedule
from .meeting import Day, parse_time
from .mpcs import (
    BASE_URL,
    CatalogUnavailable,
    fetch_catalog,
    fetch_quarters,
    parse_quarter,
)
from .solver import Preferences, search


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Search a course catalog and check for schedule conflicts."
    )
    parser.add_argument("--csv", default=None, help="Catalog CSV (default: bundled).")
    parser.add_argument(
        "--quarter",
        default=None,
        metavar="YEAR/SEASON",
        help="Fetch this quarter live from mpcs-courses.cs.uchicago.edu, "
        "e.g. 2026-27/winter. Use 'current' for the newest published quarter.",
    )
    parser.add_argument(
        "--list-quarters",
        action="store_true",
        help="List the quarters the site has published, then exit.",
    )
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

    builder = parser.add_argument_group(
        "schedule builder",
        "Search for conflict-free schedules instead of filtering the catalog.",
    )
    builder.add_argument(
        "--build",
        type=int,
        metavar="N",
        help="Find the best schedules of N courses.",
    )
    builder.add_argument(
        "--require",
        default="",
        help="Courses that must appear. Base code ('MPCS 55001', any section) "
        "or exact section ('MPCS 55001-2').",
    )
    builder.add_argument(
        "--among", default="", help="Only draw the rest from these courses."
    )
    builder.add_argument("--no-earlier-than", help="e.g. 10:00am")
    builder.add_argument("--no-later-than", help="e.g. 8:00pm")
    builder.add_argument("--days-off", default="", help="e.g. Fri,Mon")
    builder.add_argument(
        "--strict-days-off",
        action="store_true",
        help="Treat --days-off as a hard constraint rather than a penalty.",
    )
    builder.add_argument(
        "--prefer-instructor", default="", help="Comma-separated names."
    )
    builder.add_argument(
        "--options", type=int, default=3, help="How many schedules to show."
    )
    builder.add_argument(
        "--include-unscheduled",
        action="store_true",
        help="Allow courses with no published meeting time. They conflict with "
        "nothing and so score zero, which outranks every real timetable.",
    )
    args = parser.parse_args(argv)

    if args.list_quarters:
        try:
            quarters = fetch_quarters()
        except CatalogUnavailable as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"{len(quarters)} quarter(s) published at {BASE_URL}:")
        for quarter in quarters:
            print(f"  {quarter.slug:<18} {quarter.label}")
        return 0

    source = "the bundled snapshot"
    try:
        if args.quarter:
            quarter = (
                fetch_quarters()[0]
                if args.quarter.lower() in {"current", "latest", "newest"}
                else parse_quarter(args.quarter)
            )
            catalog = fetch_catalog(quarter)
            source = f"{quarter.label}, live from the department"
        elif args.csv:
            catalog = Catalog.from_csv(args.csv)
            source = args.csv
        else:
            catalog = Catalog.bundled()
    except CatalogUnavailable as exc:
        print(f"error: {exc}", file=sys.stderr)
        print(
            "hint: --list-quarters shows what has been published.", file=sys.stderr
        )
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(f"{len(catalog)} course(s) from {source}.")
    without_times = [c for c in catalog if not c.meetings]
    if without_times:
        # Stdout, not stderr: it belongs immediately under the count it
        # qualifies, and interleaving the two streams put it above.
        print(
            f"  {len(without_times)} of them have no published meeting time "
            "yet, so they cannot be placed on a timetable."
        )

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

    if args.build:
        try:
            prefs = Preferences(
                no_earlier_than=(
                    parse_time(args.no_earlier_than) if args.no_earlier_than else None
                ),
                no_later_than=(
                    parse_time(args.no_later_than) if args.no_later_than else None
                ),
                days_off=frozenset(
                    Day.parse(d) for d in args.days_off.split(",") if d.strip()
                ),
                require_days_off=args.strict_days_off,
                preferred_instructors=frozenset(
                    n.strip() for n in args.prefer_instructor.split(",") if n.strip()
                ),
            )
            result = search(
                catalog,
                args.build,
                required=[c.strip() for c in args.require.split(",") if c.strip()],
                among=(
                    [c.strip() for c in args.among.split(",") if c.strip()]
                    if args.among
                    else None
                ),
                preferences=prefs,
                limit=args.options,
                include_unscheduled=args.include_unscheduled,
            )
            options = result.options
        except (KeyError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2

        if not options:
            print(
                f"No conflict-free schedule of {args.build} course(s) exists "
                "under those constraints."
            )
            if result.unscheduled_excluded:
                print(
                    f"{result.unscheduled_excluded} course(s) were set aside "
                    "for having no published meeting time. The department "
                    "posts the course list before it sets the times."
                )
            return 1

        print(f"{len(options)} best schedule(s) of {args.build}, cheapest first:")
        for i, option in enumerate(options, start=1):
            codes = ", ".join(c.code for c in option.courses)
            print(f"\n{i}. {codes}")
            print(option.render())
        print(f"\nsearched {result.nodes:,} nodes")
        if result.unscheduled_excluded:
            print(
                f"{result.unscheduled_excluded} course(s) set aside: no "
                "published meeting time."
            )
        if not result.proven_optimal:
            print(
                "note: the node budget ran out, so these are the best found, "
                "not provably the best that exist. Narrow the pool with "
                "--among or --require to search exhaustively."
            )
        return 0

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
