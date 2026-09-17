"""Search a course catalog and build a conflict-free schedule."""

from .catalog import Catalog, Course, build_schedule
from .meeting import Day, Meeting, format_time, parse_time
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
    "Course",
    "Day",
    "Meeting",
    "Preferences",
    "ScheduleOption",
    "SearchResult",
    "build_schedule",
    "format_time",
    "parse_time",
    "score",
    "search",
    "sections_by_course",
    "solve",
]

__version__ = "0.2.0"
