"""Read the live MPCS catalog instead of a CSV that ages.

The bundled CSV was a snapshot, so the schedule it built drifted out of date
the moment the department published a new quarter. This fetches the real
listing from <https://mpcs-courses.cs.uchicago.edu/>, for any quarter back to
2015-16.

There is no API, so this parses the HTML table. Three things about that table
are worth knowing, because each one was a wrong guess first:

**Multiple meetings are separated by `<br/>` inside one cell.** A course that
meets twice a week reads
`Tuesday 2pm - 3:20pm<br/>Thursday 2pm - 3:20pm`, and stripping tags before
splitting glues them into `3:20pmThursday`, which parses as nothing. The split
happens on the markup.

**Minutes are omitted when they are zero.** `Monday 6pm - 8pm` sits beside
`Monday 5:30pm - 8:30pm` on the same page, so the time parser has to accept
both -- see `parse_time`.

**A course may have no meeting time at all**, and a room may be `—`. Both are
normal: the listing goes up before rooms are assigned, and some courses are
arranged with the instructor. They are kept, with no meetings, rather than
dropped -- a course you cannot place on a calendar is still a course you can
search for.

Parsing is separate from fetching, so every test runs on saved HTML with no
network.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from .catalog import Catalog, Course
from .meeting import Meeting

BASE_URL = "https://mpcs-courses.cs.uchicago.edu"

#: `<td>` cells in the listing, in order.
_ROW_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S)
_CELL_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S)
_TBODY_RE = re.compile(r"<tbody[^>]*>(.*?)</tbody>", re.S)
_TAG_RE = re.compile(r"<[^>]+>")
_BR_RE = re.compile(r"<br\s*/?>", re.I)
#: `/2026-27/autumn/courses` links, which is how the archive lists quarters.
_QUARTER_HREF_RE = re.compile(r'href="/(\d{4}-\d{2})/(autumn|winter|spring|summer)/courses"')

#: Rooms are written as an em dash before they are assigned.
_UNASSIGNED = {"", "—", "-", "TBA", "TBD"}


class Season(StrEnum):
    """Ordered as the academic year runs, not alphabetically."""

    AUTUMN = "autumn"
    WINTER = "winter"
    SPRING = "spring"
    SUMMER = "summer"


#: Sort key, so quarters order the way a student thinks about them.
_SEASON_ORDER = {s: i for i, s in enumerate(Season)}


@dataclass(frozen=True, order=True)
class Quarter:
    """One academic quarter, e.g. autumn of 2026-27.

    `year` is the *academic* year label the site uses (`2026-27`), not a
    calendar year: autumn 2026 and spring 2027 belong to the same one.
    """

    year: str
    season: Season

    @property
    def sort_key(self) -> tuple[str, int]:
        return (self.year, _SEASON_ORDER[self.season])

    @property
    def slug(self) -> str:
        return f"{self.year}/{self.season.value}"

    @property
    def url(self) -> str:
        return f"{BASE_URL}/{self.slug}/courses"

    @property
    def label(self) -> str:
        return f"{self.season.value.title()} {self.year}"

    def __str__(self) -> str:
        return self.slug


def parse_quarter(text: str) -> Quarter:
    """Read `2026-27/autumn`, `2026-27 autumn`, or `autumn-2026-27`."""
    parts = [p for p in re.split(r"[\s/,]+", text.strip().lower()) if p]
    year = next((p for p in parts if re.fullmatch(r"\d{4}-\d{2}", p)), None)
    season = next((p for p in parts if p in {s.value for s in Season}), None)
    if year is None or season is None:
        raise ValueError(
            f"cannot read a quarter from {text!r}; expected something like "
            "'2026-27/autumn'"
        )
    return Quarter(year=year, season=Season(season))


def _text(html: str) -> str:
    """Visible text of a fragment, with entities and whitespace normalised."""
    plain = _TAG_RE.sub("", html)
    for entity, char in (
        ("&amp;", "&"), ("&nbsp;", " "), ("&#39;", "'"), ("&quot;", '"'),
        ("&lt;", "<"), ("&gt;", ">"), ("&mdash;", "—"),
    ):
        plain = plain.replace(entity, char)
    return " ".join(plain.split())


def parse_meeting_times(cell_html: str) -> tuple[Meeting, ...]:
    """Meetings from one table cell.

    Split on `<br/>` *before* stripping tags: the two weekly meetings of a
    course are one cell separated by a line break, and flattening first turns
    `3:20pm<br/>Thursday` into `3:20pmThursday`.
    """
    meetings = []
    for part in _BR_RE.split(cell_html):
        text = _text(part)
        if not text:
            continue
        meetings.append(Meeting.parse(text))
    return tuple(meetings)


def parse_listing(html: str) -> list[Course]:
    """Courses from a quarter's listing page.

    A row whose meeting time cannot be parsed is reported, not silently
    dropped: a format change upstream should be visible rather than look like
    a quarter with fewer courses.
    """
    body = _TBODY_RE.search(html)
    if body is None:
        raise ValueError("no course table found; the page layout may have changed")

    courses: list[Course] = []
    problems: list[str] = []
    for row_html in _ROW_RE.findall(body.group(1)):
        cells = _CELL_RE.findall(row_html)
        if len(cells) < 5:
            continue
        code = _text(cells[0])
        if not code:
            continue
        location = _text(cells[3])
        try:
            meetings = parse_meeting_times(cells[4])
        except ValueError as exc:
            problems.append(f"{code}: {exc}")
            continue
        courses.append(
            Course(
                code=code,
                name=_text(cells[1]),
                instructor=_text(cells[2]),
                location="" if location in _UNASSIGNED else location,
                meetings=meetings,
            )
        )

    if problems and not courses:
        raise ValueError(
            "no row in the listing could be parsed: " + "; ".join(problems[:3])
        )
    if problems:
        raise UnparsedRows(courses, problems)
    return courses


class UnparsedRows(ValueError):
    """Some rows parsed and some did not.

    Carries the courses that worked, so a caller can choose between using a
    partial catalog and failing. Swallowing the bad rows would make an
    upstream format change look like a quiet, smaller quarter.
    """

    def __init__(self, courses: list[Course], problems: list[str]) -> None:
        super().__init__(f"{len(problems)} row(s) could not be parsed")
        self.courses = courses
        self.problems = problems


def parse_quarters(html: str) -> list[Quarter]:
    """Every quarter linked from the archive page, most recent first."""
    found = {
        Quarter(year=year, season=Season(season))
        for year, season in _QUARTER_HREF_RE.findall(html)
    }
    return sorted(found, key=lambda q: q.sort_key, reverse=True)


def catalog_from_listing(html: str) -> Catalog:
    """A `Catalog` from listing HTML, tolerating unparsed rows."""
    try:
        return Catalog(parse_listing(html))
    except UnparsedRows as partial:
        return Catalog(partial.courses)


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #
#
# Everything above is pure: it turns HTML into courses. Everything below
# fetches that HTML. Keeping the seam here is what lets the tests replay saved
# pages with no network and no flakiness, and what makes a format change a
# parsing test rather than an integration failure.

DEFAULT_TIMEOUT = 20.0

#: Enough to identify the client. A scraper with no user agent is impolite and
#: the first thing an operator blocks.
USER_AGENT = (
    "course-catalog/0.3 (+https://github.com/anita-huangz/anita-huangz.github.io)"
)


class CatalogUnavailable(RuntimeError):
    """The catalog could not be fetched. Carries the URL that failed."""

    def __init__(self, url: str, reason: str) -> None:
        super().__init__(f"could not fetch {url}: {reason}")
        self.url = url
        self.reason = reason


def _get(url: str, client=None, timeout: float = DEFAULT_TIMEOUT) -> str:
    import httpx

    owned = client is None
    client = client or httpx.Client(
        follow_redirects=True, headers={"User-Agent": USER_AGENT}, timeout=timeout
    )
    try:
        response = client.get(url)
        response.raise_for_status()
        return response.text
    except httpx.HTTPStatusError as exc:
        # A 404 on a quarter that has not been published yet is the common
        # case, and it deserves a better message than a stack trace.
        raise CatalogUnavailable(url, f"HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise CatalogUnavailable(url, str(exc) or type(exc).__name__) from exc
    finally:
        if owned:
            client.close()


def fetch_catalog(
    quarter: Quarter | str,
    *,
    client=None,
    timeout: float = DEFAULT_TIMEOUT,
) -> Catalog:
    """Live catalog for one quarter."""
    if isinstance(quarter, str):
        quarter = parse_quarter(quarter)
    return catalog_from_listing(_get(quarter.url, client=client, timeout=timeout))


def fetch_quarters(*, client=None, timeout: float = DEFAULT_TIMEOUT) -> list[Quarter]:
    """Every published quarter, most recent first.

    Read from the archive page plus the front page, because the current and
    upcoming quarters are linked from the front page and are not always in the
    archive yet -- which is exactly the quarter someone is most likely to want.
    """
    found: set[Quarter] = set()
    failures: list[str] = []
    for url in (f"{BASE_URL}/archive", BASE_URL):
        try:
            found.update(parse_quarters(_get(url, client=client, timeout=timeout)))
        except CatalogUnavailable as exc:
            failures.append(exc.reason)
    if not found:
        # Distinguish "could not reach the site" from "reached it and found
        # nothing". The first is the user's network, the second is a layout
        # change upstream, and they need different responses.
        raise CatalogUnavailable(
            BASE_URL,
            "; ".join(failures) if failures else "no quarters linked from the site",
        )
    return sorted(found, key=lambda q: q.sort_key, reverse=True)


def current_quarter(today=None, *, client=None) -> Quarter:
    """The newest quarter the site has published.

    Deliberately asks the site rather than computing it from the date: the
    department decides when a quarter appears, and guessing from the calendar
    would ask for a page that does not exist yet.
    """
    return fetch_quarters(client=client)[0]
