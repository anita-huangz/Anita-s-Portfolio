"""Courses, the catalog, and schedule building."""

from __future__ import annotations

import csv
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from importlib import resources
from pathlib import Path

from .meeting import Meeting

REQUIRED_COLUMNS = {"code", "name", "instructor", "location", "meeting times"}


@dataclass(frozen=True)
class Course:
    code: str
    name: str
    instructor: str
    location: str
    meetings: tuple[Meeting, ...] = field(default_factory=tuple)

    @classmethod
    def from_row(cls, row: dict[str, str]) -> Course:
        missing = REQUIRED_COLUMNS - set(row)
        if missing:
            raise ValueError(f"row is missing column(s) {sorted(missing)}")

        raw = (row["meeting times"] or "").strip()
        meetings = tuple(
            Meeting.parse(part) for part in raw.split(";") if part.strip()
        )
        return cls(
            code=row["code"].strip(),
            name=row["name"].strip(),
            instructor=row["instructor"].strip(),
            location=row["location"].strip(),
            meetings=meetings,
        )

    @property
    def subject(self) -> str:
        """'MPCS' from 'MPCS 53112-1'."""
        return self.code.split()[0] if self.code.split() else ""

    @property
    def number(self) -> str:
        """'53112-1' from 'MPCS 53112-1'."""
        parts = self.code.split(None, 1)
        return parts[1] if len(parts) > 1 else ""

    @property
    def base_code(self) -> str:
        """'MPCS 55001' from 'MPCS 55001-2'.

        Sections of one course share a base code. They are alternatives -- you
        take one of them -- which is what makes scheduling a search over
        choices rather than a filter over rows.
        """
        return self.code.split("-")[0].strip()

    @property
    def section(self) -> str:
        """'2' from 'MPCS 55001-2', or '' if the code carries no section."""
        parts = self.code.split("-", 1)
        return parts[1].strip() if len(parts) > 1 else ""

    def conflicts_with(self, other: Course) -> bool:
        return any(a.overlaps(b) for a in self.meetings for b in other.meetings)

    def __str__(self) -> str:
        when = ", ".join(str(m) for m in self.meetings) or "unscheduled"
        return f"{self.code}: {self.name} ({when})"


class Catalog:
    """A searchable collection of courses."""

    def __init__(self, courses: Iterable[Course]) -> None:
        self.courses: list[Course] = list(courses)

    def __len__(self) -> int:
        return len(self.courses)

    def __iter__(self) -> Iterator[Course]:
        return iter(self.courses)

    # ------------------------------------------------------------------ #
    # Loading
    # ------------------------------------------------------------------ #

    @classmethod
    def from_csv(cls, path: str | Path) -> Catalog:
        file_path = Path(path)
        if not file_path.exists():
            raise FileNotFoundError(f"no catalog CSV at {file_path}")
        with file_path.open(newline="", encoding="utf-8") as handle:
            return cls(cls._read(handle))

    @classmethod
    def bundled(cls) -> Catalog:
        """The catalog shipped with the package.

        Read through importlib.resources rather than a path relative to
        __file__: the previous version resolved "data/courses.csv" against the
        module's own directory, which pointed at a folder that did not exist,
        so the default argument could never load.
        """
        source = resources.files("course_catalog").joinpath("data/courses.csv")
        with resources.as_file(source) as path, path.open(
            newline="", encoding="utf-8"
        ) as handle:
            return cls(cls._read(handle))

    @staticmethod
    def _read(handle) -> list[Course]:
        reader = csv.DictReader(handle)
        courses: list[Course] = []
        for line_number, row in enumerate(reader, start=2):
            try:
                courses.append(Course.from_row(row))
            except ValueError as exc:
                raise ValueError(f"line {line_number}: {exc}") from exc
        return courses

    # ------------------------------------------------------------------ #
    # Search
    # ------------------------------------------------------------------ #

    def _candidates(self, schedule: Iterable[Course] | None) -> list[Course]:
        if schedule is None:
            return self.courses
        return self.without_conflicts(schedule)

    def without_conflicts(self, schedule: Iterable[Course]) -> list[Course]:
        """Courses that fit alongside everything already scheduled.

        A course already in the schedule is excluded -- it conflicts with
        itself, and offering to add it again is never useful.
        """
        booked = list(schedule)
        booked_codes = {course.code for course in booked}
        return [
            course
            for course in self.courses
            if course.code not in booked_codes
            and not any(course.conflicts_with(other) for other in booked)
        ]

    def by_code(
        self, prefix: str, schedule: Iterable[Course] | None = None
    ) -> list[Course]:
        """Courses whose code *starts with* the prefix, case-insensitively.

        The previous version used `prefix in course.code`, a substring test.
        Searching "530" matched "MPCS 53014-1" because the digits appear in the
        middle, so a prefix search silently behaved like a contains search.
        Matching is tried against the full code and against the number alone,
        so both "MPCS 530" and "530" work.
        """
        needle = prefix.strip().lower()
        if not needle:
            return []
        return [
            course
            for course in self._candidates(schedule)
            if course.code.lower().startswith(needle)
            or course.number.lower().startswith(needle)
        ]

    def by_keyword(
        self, keyword: str, schedule: Iterable[Course] | None = None
    ) -> list[Course]:
        """Courses whose title or instructor contains the keyword."""
        needle = keyword.strip().lower()
        if not needle:
            return []
        return [
            course
            for course in self._candidates(schedule)
            if needle in course.name.lower() or needle in course.instructor.lower()
        ]

    def by_day(self, day, schedule: Iterable[Course] | None = None) -> list[Course]:
        """Courses meeting on a given day."""
        return [
            course
            for course in self._candidates(schedule)
            if any(m.day is day for m in course.meetings)
        ]


def build_schedule(catalog: Catalog, codes: Iterable[str]) -> list[Course]:
    """Resolve course codes to courses, rejecting unknown or conflicting ones.

    Fails loudly. A schedule that silently dropped an unknown code would look
    conflict-free for the wrong reason.
    """
    by_code = {course.code: course for course in catalog}
    schedule: list[Course] = []

    for code in codes:
        course = by_code.get(code)
        if course is None:
            raise KeyError(f"no course with code {code!r}")
        # Two sections of the same course are not two courses. Their times
        # rarely overlap -- that is the point of offering two -- so a pure
        # conflict check happily enrolled you in Algorithms twice, under two
        # different instructors.
        duplicate = next(
            (c for c in schedule if c.base_code == course.base_code), None
        )
        if duplicate is not None:
            raise ValueError(
                f"{course.code} is another section of {duplicate.code}; "
                "pick one"
            )
        clash = next((c for c in schedule if c.conflicts_with(course)), None)
        if clash is not None:
            raise ValueError(f"{course.code} conflicts with {clash.code}")
        schedule.append(course)

    return schedule
