"""Search a course catalog and build a conflict-free schedule."""

from .catalog import Catalog, Course, build_schedule
from .meeting import Day, Meeting, format_time, parse_time

__all__ = [
    "Catalog",
    "Course",
    "Day",
    "Meeting",
    "build_schedule",
    "format_time",
    "parse_time",
]

__version__ = "0.2.0"
