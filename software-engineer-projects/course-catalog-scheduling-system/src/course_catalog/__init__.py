"""Search a course catalog and build a conflict-free schedule."""

from .catalog import Catalog, Course, build_schedule
from .meeting import (
    Day,
    Meeting,
    format_clock_time,
    format_time,
    parse_time,
)
from .mpcs import (
    CatalogUnavailable,
    Quarter,
    Season,
    UnparsedRows,
    catalog_from_listing,
    fetch_catalog,
    fetch_quarters,
    parse_listing,
    parse_quarter,
    parse_quarters,
)
from .solver import (
    Preferences,
    ScheduleOption,
    SearchResult,
    score,
    search,
    sections_by_course,
    solve,
)

__all__ = [
    "Catalog",
    "CatalogUnavailable",
    "Course",
    "Day",
    "Meeting",
    "Preferences",
    "Quarter",
    "ScheduleOption",
    "SearchResult",
    "Season",
    "UnparsedRows",
    "build_schedule",
    "catalog_from_listing",
    "fetch_catalog",
    "fetch_quarters",
    "format_clock_time",
    "format_time",
    "parse_listing",
    "parse_quarter",
    "parse_quarters",
    "parse_time",
    "score",
    "search",
    "sections_by_course",
    "solve",
]

__version__ = "0.3.0"
