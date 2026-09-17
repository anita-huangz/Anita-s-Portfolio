"""Tests for time parsing, overlap, search, and schedule building."""

from __future__ import annotations

import io

import pytest

from course_catalog import Catalog, Course, Day, Meeting, build_schedule, parse_time
from course_catalog.meeting import format_time

CSV = """code,name,instructor,location,"meeting times"
"MPCS 51040-1","Unix Systems","Alice Adams","Ryerson 251","Monday 5:30pm - 8:30pm"
"MPCS 51100-1","Advanced Programming","Bob Brown","Crerar 298","Monday 6:00pm - 7:30pm"
"MPCS 53112-1","Advanced Data Analytics","Carol Chen","Ryerson 176","Wednesday 5:30pm - 8:30pm"
"MPCS 55001-1","Algorithms","Alice Adams","Kent 120","Tue 5:30pm - 8:30pm;Thu 5:30pm - 8:30pm"
"MPCS 51100-2","Advanced Programming","Dan Davis","Crerar 298","Monday 7:30pm - 9:00pm"
"""


@pytest.fixture
def catalog() -> Catalog:
    return Catalog(Catalog._read(io.StringIO(CSV)))


# --------------------------------------------------------------------------- #
# Time parsing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "text,minutes",
    [
        ("12:00am", 0), ("12:30am", 30), ("1:00am", 60), ("11:59am", 719),
        ("12:00pm", 720), ("12:30pm", 750), ("1:00pm", 780), ("6:00pm", 1080),
        ("11:59pm", 1439),
    ],
)
def test_time_parsing_handles_the_noon_midnight_edges(text, minutes):
    assert parse_time(text) == minutes


def test_time_parsing_is_case_and_space_insensitive():
    assert parse_time(" 6:00PM ") == parse_time("6:00pm")


@pytest.mark.parametrize("bad", ["6pm", "25:00pm", "6:75pm", "", "noon", "13:00pm"])
def test_malformed_times_raise_rather_than_guess(bad):
    with pytest.raises(ValueError):
        parse_time(bad)


def test_format_time_round_trips():
    assert format_time(parse_time("6:05pm")) == "18:05"


# --------------------------------------------------------------------------- #
# Days and meetings
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("text", ["Monday", "monday", "Mon", "MONDAYS"])
def test_day_parsing_accepts_common_spellings(text):
    assert Day.parse(text) is Day.MONDAY


def test_unknown_day_raises():
    with pytest.raises(ValueError, match="day of the week"):
        Day.parse("Caturday")


def test_meeting_parses_a_full_description():
    meeting = Meeting.parse("Monday 6:00pm - 7:30pm")
    assert meeting.day is Day.MONDAY
    assert meeting.duration_minutes == 90
    assert str(meeting) == "Mon 18:00-19:30"


def test_meeting_that_ends_before_it_starts_is_rejected():
    with pytest.raises(ValueError, match="ends at or before"):
        Meeting.parse("Monday 7:30pm - 6:00pm")


def test_overlapping_meetings_on_the_same_day():
    a = Meeting.parse("Monday 5:30pm - 8:30pm")
    b = Meeting.parse("Monday 6:00pm - 7:30pm")
    assert a.overlaps(b) and b.overlaps(a)


def test_touching_meetings_do_not_overlap():
    """6:00-7:30 and 7:30-9:00 are back to back, not a conflict."""
    a = Meeting.parse("Monday 6:00pm - 7:30pm")
    b = Meeting.parse("Monday 7:30pm - 9:00pm")
    assert not a.overlaps(b)
    assert not b.overlaps(a)


def test_same_times_on_different_days_do_not_overlap():
    a = Meeting.parse("Monday 6:00pm - 7:30pm")
    b = Meeting.parse("Tuesday 6:00pm - 7:30pm")
    assert not a.overlaps(b)


def test_a_meeting_overlaps_itself():
    a = Meeting.parse("Monday 6:00pm - 7:30pm")
    assert a.overlaps(a)


# --------------------------------------------------------------------------- #
# Course parsing
# --------------------------------------------------------------------------- #


def test_course_parses_multiple_meeting_times(catalog):
    algorithms = next(c for c in catalog if c.code == "MPCS 55001-1")
    assert len(algorithms.meetings) == 2
    assert {m.day for m in algorithms.meetings} == {Day.TUESDAY, Day.THURSDAY}


def test_subject_and_number_split(catalog):
    course = next(c for c in catalog if c.code == "MPCS 51040-1")
    assert course.subject == "MPCS"
    assert course.number == "51040-1"


def test_missing_column_is_reported_with_the_line_number():
    bad = 'code,name,instructor\n"X 1","Thing","Someone"\n'
    with pytest.raises(ValueError, match="line 2"):
        Catalog._read(io.StringIO(bad))


def test_unparseable_meeting_time_names_the_line():
    bad = (
        'code,name,instructor,location,"meeting times"\n'
        '"X 1","Thing","Someone","Room","Someday at noon"\n'
    )
    with pytest.raises(ValueError, match="line 2"):
        Catalog._read(io.StringIO(bad))


def test_a_course_with_no_meeting_times_is_allowed(catalog):
    course = Course.from_row(
        {
            "code": "X 1", "name": "Independent Study", "instructor": "Someone",
            "location": "TBD", "meeting times": "",
        }
    )
    assert course.meetings == ()
    assert "unscheduled" in str(course)


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #


def test_code_search_is_a_prefix_not_a_substring(catalog):
    """`"530" in "MPCS 53014-1"` was True; a prefix search must not match that."""
    assert catalog.by_code("MPCS 511") != []
    # "112" appears inside "MPCS 53112-1" but is not a prefix of the number.
    assert catalog.by_code("112") == []


def test_code_search_matches_the_bare_number_too(catalog):
    assert [c.code for c in catalog.by_code("51040")] == ["MPCS 51040-1"]


def test_code_search_is_case_insensitive(catalog):
    assert catalog.by_code("mpcs 511") == catalog.by_code("MPCS 511")


def test_empty_code_search_returns_nothing(catalog):
    assert catalog.by_code("  ") == []


def test_keyword_matches_title_and_instructor(catalog):
    assert len(catalog.by_keyword("programming")) == 2
    assert len(catalog.by_keyword("alice")) == 2


def test_keyword_is_case_insensitive(catalog):
    assert catalog.by_keyword("ALGORITHMS") == catalog.by_keyword("algorithms")


def test_day_search(catalog):
    monday = catalog.by_day(Day.MONDAY)
    assert {c.code for c in monday} == {"MPCS 51040-1", "MPCS 51100-1", "MPCS 51100-2"}


# --------------------------------------------------------------------------- #
# Conflicts
# --------------------------------------------------------------------------- #


def test_conflicting_course_is_excluded(catalog):
    unix = next(c for c in catalog if c.code == "MPCS 51040-1")   # Mon 17:30-20:30
    free = catalog.without_conflicts([unix])
    codes = {c.code for c in free}
    assert "MPCS 51100-1" not in codes   # Mon 18:00-19:30 overlaps
    assert "MPCS 53112-1" in codes       # Wednesday, fine


def test_a_scheduled_course_is_not_offered_back(catalog):
    unix = next(c for c in catalog if c.code == "MPCS 51040-1")
    assert unix.code not in {c.code for c in catalog.without_conflicts([unix])}


def test_back_to_back_courses_are_not_a_conflict(catalog):
    first = next(c for c in catalog if c.code == "MPCS 51100-1")   # Mon 18:00-19:30
    free = {c.code for c in catalog.without_conflicts([first])}
    assert "MPCS 51100-2" in free                                   # Mon 19:30-21:00


def test_multi_day_course_conflicts_on_either_day(catalog):
    algorithms = next(c for c in catalog if c.code == "MPCS 55001-1")
    tuesday_clash = Course.from_row(
        {
            "code": "X 1", "name": "Clash", "instructor": "Someone",
            "location": "R", "meeting times": "Tuesday 6:00pm - 7:00pm",
        }
    )
    assert algorithms.conflicts_with(tuesday_clash)


def test_search_respects_the_schedule_filter(catalog):
    """Both Programming sections sit inside Unix's Monday 17:30-20:30 block."""
    unix = next(c for c in catalog if c.code == "MPCS 51040-1")
    assert len(catalog.by_keyword("programming")) == 2
    assert catalog.by_keyword("programming", [unix]) == []


def test_schedule_filter_keeps_courses_on_other_days(catalog):
    unix = next(c for c in catalog if c.code == "MPCS 51040-1")
    assert [c.code for c in catalog.by_keyword("analytics", [unix])] == ["MPCS 53112-1"]


# --------------------------------------------------------------------------- #
# Schedule building
# --------------------------------------------------------------------------- #


def test_build_schedule_resolves_codes(catalog):
    schedule = build_schedule(catalog, ["MPCS 51040-1", "MPCS 53112-1"])
    assert [c.code for c in schedule] == ["MPCS 51040-1", "MPCS 53112-1"]


def test_build_schedule_rejects_an_unknown_code(catalog):
    """Silently dropping it would make the schedule look conflict-free wrongly."""
    with pytest.raises(KeyError, match="NOPE"):
        build_schedule(catalog, ["NOPE 000"])


def test_build_schedule_rejects_a_conflict(catalog):
    with pytest.raises(ValueError, match="conflicts with"):
        build_schedule(catalog, ["MPCS 51040-1", "MPCS 51100-1"])


def test_empty_schedule_is_fine(catalog):
    assert build_schedule(catalog, []) == []


# --------------------------------------------------------------------------- #
# Bundled data
# --------------------------------------------------------------------------- #


def test_the_bundled_catalog_loads():
    """The old default path resolved to a directory that did not exist."""
    bundled = Catalog.bundled()
    assert len(bundled) > 0
    assert all(c.code for c in bundled)


def test_every_bundled_course_has_parseable_meetings():
    for course in Catalog.bundled():
        for meeting in course.meetings:
            assert meeting.end > meeting.start
