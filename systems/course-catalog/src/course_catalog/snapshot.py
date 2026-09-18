"""Write a fetched catalog back out as CSV.

The bundled `data/courses.csv` is the offline default, so CI and anyone
without a network can still run everything. It used to be hand-maintained,
which is why it went stale: the department publishes a new quarter and the
file does not change. This regenerates it from the live listing.

`python -m course_catalog.snapshot --quarter current`
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from .catalog import REQUIRED_COLUMNS, Catalog, Course
from .mpcs import CatalogUnavailable, fetch_catalog, fetch_quarters, parse_quarter

#: Column order the reader expects.
COLUMNS = ["code", "name", "instructor", "location", "meeting times"]
BUNDLED = Path(__file__).parent / "data" / "courses.csv"


def write_csv(courses: list[Course], path: Path) -> None:
    """Write courses in the form `Catalog.from_csv` reads back.

    Meetings are written with `to_catalog_text`, not `str`: the display form
    is 24-hour and `Meeting.parse` cannot read it, so a snapshot written the
    obvious way produces a file that will not load.
    """
    assert set(COLUMNS) == REQUIRED_COLUMNS, "column list drifted from the reader"
    with path.open("w", newline="", encoding="utf-8") as handle:
        # `csv` defaults to CRLF. Git normalises it on commit, so the file on
        # disk would differ from the committed one and the weekly refresh
        # would report a change on every run.
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(COLUMNS)
        for course in sorted(courses, key=lambda c: c.code):
            writer.writerow(
                [
                    course.code,
                    course.name,
                    course.instructor,
                    course.location,
                    "; ".join(m.to_catalog_text() for m in course.meetings),
                ]
            )


def newest_scheduled_quarter(*, client=None, minimum: int = 10):
    """The newest quarter that actually has meeting times.

    The course list for a quarter goes up months before the times do, so the
    newest quarter is often entirely unscheduled -- useless as a snapshot for
    a timetable builder. This walks back until it finds one with real times.
    """
    for quarter in fetch_quarters(client=client):
        catalog = fetch_catalog(quarter, client=client)
        if sum(1 for c in catalog if c.meetings) >= minimum:
            return quarter, catalog
    raise CatalogUnavailable("", "no quarter has published meeting times")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--quarter",
        default="current",
        help="A quarter like 2026-27/autumn, or 'current' for the newest one "
        "with published meeting times (default: %(default)s).",
    )
    parser.add_argument(
        "--out", type=Path, default=BUNDLED, help="Where to write (default: bundled)."
    )
    args = parser.parse_args(argv)

    try:
        if args.quarter.lower() in {"current", "latest", "newest"}:
            quarter, catalog = newest_scheduled_quarter()
        else:
            quarter = parse_quarter(args.quarter)
            catalog = fetch_catalog(quarter)
    except (CatalogUnavailable, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    courses = list(catalog)
    write_csv(courses, args.out)

    scheduled = sum(1 for c in courses if c.meetings)
    print(
        f"{quarter.label}: {len(courses)} course(s), {scheduled} with meeting "
        f"times -> {args.out}"
    )
    # Prove it reads back, rather than trusting that it will.
    reread = Catalog.from_csv(args.out)
    if len(reread) != len(courses):
        print(
            f"error: wrote {len(courses)} courses but read back {len(reread)}",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
