"""Tests for time parsing, overlap, search, and schedule building."""

from __future__ import annotations

import io
from itertools import combinations

import pytest

from course_catalog import (
    Catalog,
    Course,
    Day,
    Meeting,
    Preferences,
    build_schedule,
    parse_time,
    score,
    search,
    sections_by_course,
    solve,
)
from course_catalog.meeting import format_time
from course_catalog.solver import _gap_minutes

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


def test_bundled_csv_is_a_real_file_not_an_lfs_pointer():
    """Guards a CI-only failure.

    The repository routes *.csv through Git LFS for its large datasets, and
    actions/checkout does not fetch LFS content by default. Under LFS this
    file arrives as a three-line pointer, the header parse fails, and the
    suite breaks in CI while passing on any machine that has the real file.
    """
    from importlib import resources

    source = resources.files("course_catalog").joinpath("data/courses.csv")
    first_line = source.read_text(encoding="utf-8").splitlines()[0]
    assert not first_line.startswith("version https://git-lfs"), (
        "courses.csv is an LFS pointer; it must be stored as a regular file"
    )
    assert first_line.startswith("code,name,instructor")


# --------------------------------------------------------------------------- #
# Sections are alternatives, not additions
# --------------------------------------------------------------------------- #


def test_base_code_strips_the_section():
    course = Course("MPCS 55001-2", "Algorithms", "A", "B")
    assert course.base_code == "MPCS 55001"
    assert course.section == "2"


def test_a_code_without_a_section_has_an_empty_section():
    assert Course("MPCS 55001", "Algorithms", "A", "B").section == ""


def test_two_sections_of_one_course_cannot_both_be_scheduled(catalog):
    """They rarely clash on time -- that is the point of offering two."""
    a, b = catalog.by_code("MPCS 51100-1")[0], catalog.by_code("MPCS 51100-2")[0]
    assert not a.conflicts_with(b)          # 6:00-7:30 then 7:30-9:00
    with pytest.raises(ValueError, match="another section"):
        build_schedule(catalog, ["MPCS 51100-1", "MPCS 51100-2"])


def test_sections_group_under_their_base_code(catalog):
    groups = sections_by_course(catalog)
    assert [c.code for c in groups["MPCS 51100"]] == [
        "MPCS 51100-1",
        "MPCS 51100-2",
    ]
    assert len(groups["MPCS 51040"]) == 1


# --------------------------------------------------------------------------- #
# The solver
# --------------------------------------------------------------------------- #


def test_the_solver_returns_only_conflict_free_schedules(catalog):
    for option in solve(catalog, 3, limit=50):
        courses = option.courses
        assert len(courses) == 3
        for i, a in enumerate(courses):
            for b in courses[i + 1 :]:
                assert not a.conflicts_with(b)
                assert a.base_code != b.base_code


def test_the_solver_finds_nothing_when_nothing_fits(catalog):
    # Only five base courses exist, so six is impossible.
    assert solve(catalog, 6) == []


def test_a_required_course_appears_in_every_option(catalog):
    options = solve(catalog, 2, required=["MPCS 55001"], limit=50)
    assert options
    assert all(
        any(c.base_code == "MPCS 55001" for c in o.courses) for o in options
    )


def test_a_required_base_code_lets_the_solver_choose_the_section():
    """The whole reason enumeration beats filtering.

    Advanced Programming is offered at 6:00 and at 7:30. A seminar at 6:30
    rules out the first section and not the second, so the only way to schedule
    both courses is for the solver to switch sections -- which no filter over
    the catalog can do.
    """
    csv = (
        'code,name,instructor,location,"meeting times"\n'
        '"MPCS 51100-1","Advanced Programming","Bob","C1","Monday 6:00pm - 7:30pm"\n'
        '"MPCS 51100-2","Advanced Programming","Dan","C1","Monday 7:30pm - 9:00pm"\n'
        '"MPCS 50000-1","Seminar","Eve","C2","Monday 6:30pm - 7:00pm"\n'
    )
    small = Catalog(Catalog._read(io.StringIO(csv)))
    options = solve(small, 2, required=["MPCS 51100"], limit=50)
    assert [
        tuple(sorted(c.code for c in o.courses)) for o in options
    ] == [("MPCS 50000-1", "MPCS 51100-2")]


def test_every_section_of_a_required_course_being_blocked_yields_nothing(catalog):
    # Unix runs 5:30-8:30 Monday, which swallows both Advanced Programming
    # sections. There is no schedule containing them both.
    assert solve(catalog, 2, required=["MPCS 51100"], among=["MPCS 51040"]) == []


def test_a_required_exact_section_is_honoured(catalog):
    options = solve(catalog, 1, required=["MPCS 51100-2"], limit=50)
    assert [o.courses[0].code for o in options] == ["MPCS 51100-2"]


def test_requiring_more_courses_than_the_schedule_holds_is_an_error(catalog):
    with pytest.raises(ValueError, match="do not fit"):
        solve(catalog, 1, required=["MPCS 51040", "MPCS 55001"])


def test_requiring_the_same_course_twice_is_an_error(catalog):
    with pytest.raises(ValueError, match="required twice"):
        solve(catalog, 2, required=["MPCS 51100-1", "MPCS 51100-2"])


def test_an_unknown_required_course_raises(catalog):
    with pytest.raises(KeyError):
        solve(catalog, 2, required=["MPCS 99999"])


def test_size_must_be_positive(catalog):
    with pytest.raises(ValueError, match="at least 1"):
        solve(catalog, 0)


# --------------------------------------------------------------------------- #
# Preferences
# --------------------------------------------------------------------------- #


def test_options_come_back_cheapest_first(catalog):
    options = solve(catalog, 2, limit=50)
    assert [o.cost for o in options] == sorted(o.cost for o in options)


def test_a_morning_preference_penalises_early_classes():
    early = Course("A 1-1", "Early", "x", "y", (Meeting.parse("Monday 8:00am - 9:00am"),))
    late = Course("B 1-1", "Late", "x", "y", (Meeting.parse("Monday 2:00pm - 3:00pm"),))
    prefs = Preferences(no_earlier_than=parse_time("10:00am"), minimize_days=False,
                        minimize_gaps=False)
    assert score([early], prefs)[1]["too_early"] == 120   # two hours too early
    assert score([late], prefs)[1]["too_early"] == 0


def test_an_evening_limit_penalises_the_overrun_only():
    course = Course("A 1-1", "Night", "x", "y",
                    (Meeting.parse("Monday 7:00pm - 9:30pm"),))
    prefs = Preferences(no_later_than=parse_time("9:00pm"))
    # 30 minutes past the limit, not the whole class.
    assert score([course], prefs)[1]["too_late"] == 30


def test_a_soft_day_off_is_a_penalty_not_an_exclusion(catalog):
    options = solve(
        catalog, 1, among=["MPCS 51040"],
        preferences=Preferences(days_off=frozenset({Day.MONDAY})),
    )
    # Still offered -- with the cost shown -- rather than silently dropped.
    assert options and options[0].breakdown["day_off"] > 0


def test_a_strict_day_off_excludes_the_course(catalog):
    options = solve(
        catalog, 1, among=["MPCS 51040"],
        preferences=Preferences(
            days_off=frozenset({Day.MONDAY}), require_days_off=True
        ),
    )
    assert options == []


def test_fewer_days_on_campus_costs_less(catalog):
    prefs = Preferences(minimize_gaps=False)
    one_day = catalog.by_code("MPCS 51040")      # Monday only
    two_days = catalog.by_code("MPCS 55001")     # Tue and Thu
    assert score(one_day, prefs)[0] < score(two_days, prefs)[0]


def test_gaps_count_only_the_time_between_classes():
    first = Course("A 1-1", "First", "x", "y",
                   (Meeting.parse("Monday 9:00am - 10:00am"),))
    second = Course("B 1-1", "Second", "x", "y",
                    (Meeting.parse("Monday 11:30am - 12:30pm"),))
    assert _gap_minutes([first, second]) == 90
    # Nothing before the first class or after the last is a gap.
    assert _gap_minutes([first]) == 0
    # Neither is time on a different day.
    other_day = Course("C 1-1", "Other", "x", "y",
                       (Meeting.parse("Tuesday 5:00pm - 6:00pm"),))
    assert _gap_minutes([first, other_day]) == 0


def test_back_to_back_classes_have_no_gap():
    a = Course("A 1-1", "A", "x", "y", (Meeting.parse("Monday 6:00pm - 7:30pm"),))
    b = Course("B 1-1", "B", "x", "y", (Meeting.parse("Monday 7:30pm - 9:00pm"),))
    assert _gap_minutes([a, b]) == 0


def test_a_preferred_instructor_lowers_the_cost(catalog):
    alice = catalog.by_code("MPCS 51040")        # Alice Adams
    prefs = Preferences(preferred_instructors=frozenset({"Alice"}))
    assert score(alice, prefs)[1]["instructor"] == 0
    bob = catalog.by_code("MPCS 51100-1")        # Bob Brown
    assert score(bob, prefs)[1]["instructor"] > 0


def test_the_breakdown_sums_to_the_cost(catalog):
    prefs = Preferences(no_earlier_than=parse_time("10:00am"),
                        days_off=frozenset({Day.MONDAY}))
    for option in solve(catalog, 2, preferences=prefs, limit=50):
        assert option.cost == pytest.approx(sum(option.breakdown.values()))


def test_an_option_reports_its_own_shape(catalog):
    option = solve(catalog, 1, required=["MPCS 55001"])[0]
    assert option.days_used == (Day.TUESDAY, Day.THURSDAY)
    assert option.earliest_start == parse_time("5:30pm")
    assert option.latest_end == parse_time("8:30pm")
    assert "Tue" in option.render()


def test_the_node_budget_stops_the_search(catalog):
    # A budget of zero still lets the first branch complete, but the result
    # set must be a subset of the unbounded one rather than wrong.
    bounded = solve(catalog, 2, limit=50, node_budget=0)
    unbounded = solve(catalog, 2, limit=50)
    assert len(bounded) <= len(unbounded)
    codes = {tuple(sorted(c.code for c in o.courses)) for o in unbounded}
    assert all(tuple(sorted(c.code for c in o.courses)) in codes for o in bounded)


# --------------------------------------------------------------------------- #
# The search is an anytime algorithm and says so
# --------------------------------------------------------------------------- #


def test_a_small_catalog_search_is_proven_optimal(catalog):
    result = search(catalog, 2, limit=5)
    assert result.proven_optimal
    assert result.nodes > 0


def test_exhausting_the_budget_is_reported_not_hidden(catalog):
    result = search(catalog, 2, limit=5, node_budget=1)
    assert not result.proven_optimal
    # Still returns what it found rather than nothing: the budget does not
    # fire until at least one complete schedule exists.
    assert result.options


def test_an_impossible_search_terminates_instead_of_hunting_forever(catalog):
    # Nothing to find, so the "keep going until you have one" rule cannot be
    # satisfied -- the hard ceiling has to stop it.
    result = search(catalog, 6, limit=5, node_budget=1)
    assert result.options == []


def test_the_bound_never_prunes_the_optimum():
    """Branch-and-bound must not change the answer, only the work done.

    Checked against brute force: every conflict-free combination, scored.
    """
    csv_rows = ['code,name,instructor,location,"meeting times"']
    slots = [
        "9:00am - 10:30am",
        "11:00am - 12:30pm",
        "2:00pm - 3:30pm",
        "5:30pm - 7:00pm",
    ]
    days = ["Monday", "Tuesday", "Wednesday"]
    for i in range(12):
        csv_rows.append(
            f'"X {100 + i}-1","C{i}","P{i}","R","{days[i % 3]} {slots[i % 4]}"'
        )
    small = Catalog(Catalog._read(io.StringIO("\n".join(csv_rows))))

    prefs = Preferences(no_earlier_than=parse_time("10:00am"))
    brute = []
    for combo in combinations(list(small), 3):
        if any(
            a.conflicts_with(b)
            for i, a in enumerate(combo)
            for b in combo[i + 1 :]
        ):
            continue
        brute.append(score(combo, prefs)[0])
    brute.sort()

    found = search(small, 3, preferences=prefs, limit=5, node_budget=10**9)
    assert found.proven_optimal
    assert [o.cost for o in found.options] == pytest.approx(brute[:5])


def test_the_gap_bound_stays_admissible():
    """Gaps shrink when a course lands in one, so the bound must allow for it.

    A bound that assumed gaps only grow would prune the schedule that fills
    the gap -- which is usually the best one.
    """
    csv = (
        'code,name,instructor,location,"meeting times"\n'
        '"X 1-1","Morning","P","R","Monday 9:00am - 10:00am"\n'
        '"X 2-1","Evening","P","R","Monday 5:00pm - 6:00pm"\n'
        '"X 3-1","Filler","P","R","Monday 10:30am - 4:30pm"\n'
        '"X 4-1","Elsewhere","P","R","Tuesday 9:00am - 10:00am"\n'
    )
    small = Catalog(Catalog._read(io.StringIO(csv)))
    result = search(small, 3, limit=10, node_budget=10**9)
    assert result.proven_optimal
    best = result.options[0]
    # Filling the 7-hour gap beats adding a second day.
    assert {c.code for c in best.courses} == {"X 1-1", "X 2-1", "X 3-1"}
