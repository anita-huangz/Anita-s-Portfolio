"""The live MPCS catalog: quarter handling, HTML parsing, and fetching.

Every test runs offline. The fixtures in `tests/fixtures/` are real pages
saved from <https://mpcs-courses.cs.uchicago.edu/>, so the parser is checked
against the markup it will actually meet rather than against a tidied-up
version of it. The transport is exercised through `httpx.MockTransport`, which
means the failure paths -- a 404 for an unpublished quarter, a connection that
drops -- are testable rather than hypothetical.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from course_catalog import (
    Catalog,
    CatalogUnavailable,
    Quarter,
    Season,
    UnparsedRows,
    build_schedule,
    catalog_from_listing,
    fetch_catalog,
    fetch_quarters,
    parse_listing,
    parse_quarter,
    parse_quarters,
    search,
    solve,
)
from course_catalog.mpcs import BASE_URL, parse_meeting_times

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


@pytest.fixture
def listing() -> str:
    return fixture("listing-2025-26-autumn.html")


@pytest.fixture
def archive() -> str:
    return fixture("archive.html")


def transport(routes: dict[str, tuple[int, str]]) -> httpx.MockTransport:
    """Serve saved pages by path, so no test touches the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = routes.get(request.url.path, (404, "not found"))
        return httpx.Response(status, text=body)

    return httpx.MockTransport(handler)


def client_for(routes: dict[str, tuple[int, str]]) -> httpx.Client:
    return httpx.Client(transport=transport(routes), follow_redirects=True)


# --------------------------------------------------------------------------- #
# Quarters
# --------------------------------------------------------------------------- #


def test_a_quarter_builds_its_own_url():
    q = Quarter("2026-27", Season.WINTER)
    assert q.url == f"{BASE_URL}/2026-27/winter/courses"
    assert q.slug == "2026-27/winter"
    assert q.label == "Winter 2026-27"


@pytest.mark.parametrize(
    "text",
    ["2026-27/autumn", "2026-27 autumn", "autumn 2026-27", " 2026-27, Autumn "],
)
def test_quarters_parse_from_the_ways_people_write_them(text):
    assert parse_quarter(text) == Quarter("2026-27", Season.AUTUMN)


@pytest.mark.parametrize("bad", ["", "2026-27", "autumn", "2026/autumn", "next term"])
def test_an_unreadable_quarter_raises(bad):
    with pytest.raises(ValueError, match="quarter"):
        parse_quarter(bad)


def test_quarters_sort_by_the_academic_year_not_the_alphabet():
    """Autumn comes first in a year; alphabetically it comes second."""
    order = [
        Quarter("2026-27", Season.AUTUMN),
        Quarter("2026-27", Season.WINTER),
        Quarter("2026-27", Season.SPRING),
        Quarter("2026-27", Season.SUMMER),
    ]
    assert sorted(order, key=lambda q: q.sort_key) == order


def test_every_quarter_is_read_from_the_archive(archive):
    quarters = parse_quarters(archive)
    # 2015-16 through the current year, four quarters each.
    assert len(quarters) >= 40
    assert len({q.year for q in quarters}) >= 10
    assert all(isinstance(q.season, Season) for q in quarters)


def test_the_archive_lists_newest_first(archive):
    quarters = parse_quarters(archive)
    assert quarters == sorted(quarters, key=lambda q: q.sort_key, reverse=True)


def test_quarters_from_a_page_with_no_links_are_empty():
    assert parse_quarters("<html><body>nothing here</body></html>") == []


# --------------------------------------------------------------------------- #
# Parsing the listing
# --------------------------------------------------------------------------- #


def test_the_real_listing_parses(listing):
    courses = parse_listing(listing)
    assert len(courses) == 31
    codes = {c.code for c in courses}
    assert "MPCS 55001-1" in codes
    assert all(c.code.startswith("MPCS ") for c in courses)
    assert all(c.name for c in courses)


def test_a_twice_weekly_course_keeps_both_meetings(listing):
    """The `<br/>` case.

    `Tuesday 2pm - 3:20pm<br/>Thursday 2pm - 3:20pm` is one table cell.
    Stripping the tags before splitting glues it into `3:20pmThursday`, which
    parses as nothing -- so the split has to happen on the markup.
    """
    courses = {c.code: c for c in parse_listing(listing)}
    discrete = courses["MPCS 50103-1"]
    assert len(discrete.meetings) == 2
    assert [str(m) for m in discrete.meetings] == [
        "Tue 14:00-15:20",
        "Thu 14:00-15:20",
    ]


def test_meetings_split_on_the_line_break_not_the_text():
    cell = "<span>Tuesday 11am - 12:20pm<br/>Thursday 11am - 12:20pm</span>"
    assert len(parse_meeting_times(cell)) == 2
    # Both spellings of the tag, since the source has used each.
    assert len(parse_meeting_times(cell.replace("<br/>", "<br>"))) == 2


def test_a_time_without_minutes_parses(listing):
    """`Monday 6pm - 7:30pm` is how the real page writes it."""
    courses = {c.code: c for c in parse_listing(listing)}
    advanced = courses["MPCS 51100-1"]
    assert [str(m) for m in advanced.meetings] == ["Mon 18:00-19:30"]


def test_an_unassigned_room_becomes_empty_not_an_em_dash():
    html = """
    <table><tbody>
      <tr><td><span>MPCS 12345-1</span></td><td><a href="#">Course</a></td>
          <td>Instructor</td><td>—</td>
          <td><span>Monday 6pm - 8pm</span></td></tr>
    </tbody></table>
    """
    assert parse_listing(html)[0].location == ""


def test_a_course_with_no_meeting_time_is_kept():
    """The listing goes up before every course is scheduled.

    Dropping it would make the course unsearchable; keeping it with no
    meetings means it simply never conflicts with anything.
    """
    html = """
    <table><tbody>
      <tr><td><span>MPCS 99999-1</span></td><td><a href="#">Arranged</a></td>
          <td>Staff</td><td>—</td><td></td></tr>
    </tbody></table>
    """
    courses = parse_listing(html)
    assert len(courses) == 1
    assert courses[0].meetings == ()


def test_html_entities_are_decoded():
    html = """
    <table><tbody>
      <tr><td><span>MPCS 12345-1</span></td>
          <td><a href="#">Data &amp; Systems</a></td>
          <td>O&#39;Brien</td><td>Crerar 011</td>
          <td><span>Monday 6pm - 8pm</span></td></tr>
    </tbody></table>
    """
    course = parse_listing(html)[0]
    assert course.name == "Data & Systems"
    assert course.instructor == "O'Brien"


def test_a_page_with_no_table_is_an_error_not_an_empty_catalog():
    """An empty result and a changed layout must not look the same."""
    with pytest.raises(ValueError, match="no course table"):
        parse_listing("<html><body><p>Down for maintenance</p></body></html>")


def test_an_unparseable_row_is_reported_with_the_rows_that_worked():
    html = """
    <table><tbody>
      <tr><td><span>MPCS 11111-1</span></td><td><a href="#">Good</a></td>
          <td>A</td><td>R 1</td><td><span>Monday 6pm - 8pm</span></td></tr>
      <tr><td><span>MPCS 22222-1</span></td><td><a href="#">Bad</a></td>
          <td>B</td><td>R 2</td><td><span>Someday 6pm - 8pm</span></td></tr>
    </tbody></table>
    """
    with pytest.raises(UnparsedRows) as caught:
        parse_listing(html)
    assert [c.code for c in caught.value.courses] == ["MPCS 11111-1"]
    assert "MPCS 22222-1" in caught.value.problems[0]


def test_every_row_failing_raises_rather_than_returning_nothing():
    html = """
    <table><tbody>
      <tr><td><span>MPCS 22222-1</span></td><td><a href="#">Bad</a></td>
          <td>B</td><td>R 2</td><td><span>Someday 6pm - 8pm</span></td></tr>
    </tbody></table>
    """
    with pytest.raises(ValueError, match="no row in the listing"):
        parse_listing(html)


def test_catalog_from_listing_tolerates_a_partial_page():
    html = """
    <table><tbody>
      <tr><td><span>MPCS 11111-1</span></td><td><a href="#">Good</a></td>
          <td>A</td><td>R 1</td><td><span>Monday 6pm - 8pm</span></td></tr>
      <tr><td><span>MPCS 22222-1</span></td><td><a href="#">Bad</a></td>
          <td>B</td><td>R 2</td><td><span>Someday 6pm - 8pm</span></td></tr>
    </tbody></table>
    """
    catalog = catalog_from_listing(html)
    assert len(catalog) == 1


def test_the_header_row_is_not_mistaken_for_a_course(listing):
    """It has `<th>` cells, not `<td>`, and sits outside `<tbody>`."""
    assert all("Code" not in c.code for c in parse_listing(listing))


# --------------------------------------------------------------------------- #
# Fetching
# --------------------------------------------------------------------------- #


def test_fetching_a_quarter_returns_a_usable_catalog(listing):
    client = client_for({"/2025-26/autumn/courses": (200, listing)})
    catalog = fetch_catalog("2025-26/autumn", client=client)
    assert len(catalog) == 31
    assert catalog.by_code("MPCS 55001")


def test_fetching_accepts_a_quarter_object_or_a_string(listing):
    routes = {"/2025-26/autumn/courses": (200, listing)}
    a = fetch_catalog("2025-26/autumn", client=client_for(routes))
    b = fetch_catalog(Quarter("2025-26", Season.AUTUMN), client=client_for(routes))
    assert len(a) == len(b)


def test_an_unpublished_quarter_says_so_instead_of_crashing():
    """The common case: asking for a quarter the department has not posted."""
    client = client_for({})
    with pytest.raises(CatalogUnavailable, match="HTTP 404"):
        fetch_catalog("2099-00/autumn", client=client)


def test_a_server_error_names_the_url_that_failed():
    client = client_for({"/2025-26/autumn/courses": (500, "boom")})
    with pytest.raises(CatalogUnavailable) as caught:
        fetch_catalog("2025-26/autumn", client=client)
    assert "2025-26/autumn/courses" in caught.value.url
    assert "500" in caught.value.reason


def test_a_dropped_connection_is_reported_as_unavailable():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("network is unreachable", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(CatalogUnavailable, match="unreachable"):
        fetch_catalog("2025-26/autumn", client=client)


def test_quarters_come_from_the_archive_and_the_front_page(archive, listing):
    """The current quarter is linked from the front page, not the archive.

    That is exactly the quarter someone is most likely to ask for, so reading
    only the archive would miss it.
    """
    front = '<a href="/2099-00/autumn/courses">Autumn</a>'
    client = client_for({"/archive": (200, archive), "/": (200, front)})
    quarters = fetch_quarters(client=client)
    assert Quarter("2099-00", Season.AUTUMN) in quarters
    assert quarters[0] == Quarter("2099-00", Season.AUTUMN)  # newest first


def test_quarters_still_work_when_the_archive_is_down(archive):
    front = '<a href="/2026-27/autumn/courses">Autumn</a>'
    client = client_for({"/archive": (503, "down"), "/": (200, front)})
    assert Quarter("2026-27", Season.AUTUMN) in fetch_quarters(client=client)


def test_unreachable_site_reports_the_reason_not_an_empty_list():
    """"Could not connect" and "connected, found nothing" need different fixes."""

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out", request=request)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    with pytest.raises(CatalogUnavailable, match="timed out"):
        fetch_quarters(client=client)


def test_a_reachable_site_with_no_quarters_says_that_instead():
    client = client_for({"/archive": (200, "<html></html>"), "/": (200, "<html></html>")})
    with pytest.raises(CatalogUnavailable, match="no quarters linked"):
        fetch_quarters(client=client)


# --------------------------------------------------------------------------- #
# The fetched catalog works with everything else
# --------------------------------------------------------------------------- #


def test_a_fetched_catalog_schedules_like_a_bundled_one(listing):
    catalog = catalog_from_listing(listing)
    options = solve(catalog, 3, limit=5)
    assert options
    for option in options:
        for i, a in enumerate(option.courses):
            for b in option.courses[i + 1 :]:
                assert not a.conflicts_with(b)


def test_the_real_listing_has_sections_to_choose_between(listing):
    """Which is the thing the solver is for."""
    catalog = catalog_from_listing(listing)
    algorithms = catalog.by_code("MPCS 55001")
    assert len(algorithms) == 2
    with pytest.raises(ValueError, match="another section"):
        build_schedule(catalog, [c.code for c in algorithms])


def test_searching_a_fetched_catalog_works(listing):
    catalog = catalog_from_listing(listing)
    assert catalog.by_keyword("algorithms")
    assert catalog.by_code("MPCS 530")
    assert isinstance(catalog, Catalog)


# --------------------------------------------------------------------------- #
# Courses with no published meeting time
# --------------------------------------------------------------------------- #
#
# The department publishes a quarter's course list before it sets the times.
# Winter 2026-27 went up with all thirty courses and not one meeting time, and
# that state breaks the solver in a way worth a fixture of its own.


@pytest.fixture
def unscheduled() -> str:
    return fixture("listing-2026-27-winter-unscheduled.html")


def test_a_quarter_can_be_published_with_no_times_at_all(unscheduled):
    courses = parse_listing(unscheduled)
    assert len(courses) == 30
    assert all(c.meetings == () for c in courses)
    # Not a parse failure: the cell really is `<span ...></span>`.
    assert all(c.name for c in courses)


def test_an_unplaceable_course_would_otherwise_win_every_search(unscheduled):
    """The bug this guards against.

    A course with no meeting time conflicts with nothing, occupies no day and
    leaves no gap, so it scores zero -- which beats every real timetable. Left
    in, the "best schedule" for a partly-published quarter is the one that
    schedules nothing.
    """
    scheduled = catalog_from_listing(fixture("listing-2025-26-autumn.html"))
    mixed = Catalog(list(scheduled)[:6] + list(parse_listing(unscheduled))[:6])

    honest = search(mixed, 3, limit=3)
    assert honest.unscheduled_excluded == 6
    assert all(o.cost > 0 for o in honest.options)
    assert all(
        all(c.meetings for c in o.courses) for o in honest.options
    ), "a timetable cannot contain a course with no time"

    # Opting in reproduces the zero-cost nonsense, on purpose.
    included = search(mixed, 3, limit=3, include_unscheduled=True)
    assert included.options[0].cost == 0
    assert included.unscheduled_excluded == 0


def test_a_quarter_with_no_times_yields_no_schedule_and_says_why(unscheduled):
    result = search(catalog_from_listing(unscheduled), 3, limit=5)
    assert result.options == []
    # An empty result with no explanation looks like a broken search.
    assert result.unscheduled_excluded == 30


def test_a_required_course_is_honoured_even_with_no_published_time(unscheduled):
    """Naming a course explicitly is a stronger signal than the filter."""
    result = search(catalog_from_listing(unscheduled), 1, required=["MPCS 55001"])
    assert [c.code for c in result.options[0].courses] == ["MPCS 55001-1"]


def test_searching_a_fully_scheduled_quarter_excludes_nothing():
    result = search(catalog_from_listing(fixture("listing-2025-26-autumn.html")), 3)
    assert result.unscheduled_excluded == 0
    assert result.options
