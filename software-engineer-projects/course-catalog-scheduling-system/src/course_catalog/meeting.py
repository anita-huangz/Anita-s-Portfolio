"""Meeting times and overlap.

A meeting is a day plus a half-open minute interval [start, end). Half-open is
the point: a class ending at 7:30 and another starting at 7:30 do not conflict,
and a closed interval would wrongly say they do.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import IntEnum

TIME_RE = re.compile(r"^(\d{1,2}):(\d{2})\s*([ap]m)$", re.IGNORECASE)


class Day(IntEnum):
    """Ordered so a weekly schedule sorts naturally."""

    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6

    @classmethod
    def parse(cls, text: str) -> Day:
        key = text.strip().lower()
        for day in cls:
            # Accept "Mon", "Monday", "MONDAYS".
            if key.startswith(day.name.lower()[:3]):
                return day
        raise ValueError(f"not a day of the week: {text!r}")

    @property
    def short(self) -> str:
        return self.name.title()[:3]


def parse_time(text: str) -> int:
    """Minutes since midnight, from a string like '6:00pm'.

    Raises rather than guessing: a malformed time in the catalog would
    otherwise become a plausible-looking number and silently misplace a class.
    """
    match = TIME_RE.match(text.strip())
    if not match:
        raise ValueError(f"cannot parse time: {text!r}")

    hour, minute, period = int(match[1]), int(match[2]), match[3].lower()
    if not 1 <= hour <= 12 or minute >= 60:
        raise ValueError(f"time out of range: {text!r}")

    if period == "am" and hour == 12:
        hour = 0
    elif period == "pm" and hour != 12:
        hour += 12
    return hour * 60 + minute


def format_time(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


@dataclass(frozen=True, order=True)
class Meeting:
    day: Day
    start: int
    end: int

    def __post_init__(self) -> None:
        if self.end <= self.start:
            raise ValueError(f"meeting ends at or before it starts: {self}")

    @classmethod
    def parse(cls, text: str) -> Meeting:
        """Build from 'Monday 6:00pm - 7:30pm'."""
        parts = text.strip().split(None, 1)
        if len(parts) != 2:
            raise ValueError(f"cannot parse meeting time: {text!r}")

        day_text, time_range = parts
        if "-" not in time_range:
            raise ValueError(f"meeting time needs a start and an end: {text!r}")

        start_text, end_text = time_range.split("-", 1)
        return cls(
            day=Day.parse(day_text),
            start=parse_time(start_text),
            end=parse_time(end_text),
        )

    def overlaps(self, other: Meeting) -> bool:
        if self.day is not other.day:
            return False
        # Half-open: touching at an endpoint is not an overlap.
        return self.start < other.end and other.start < self.end

    @property
    def duration_minutes(self) -> int:
        return self.end - self.start

    def __str__(self) -> str:
        return f"{self.day.short} {format_time(self.start)}-{format_time(self.end)}"
