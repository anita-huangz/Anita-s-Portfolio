"""Build a schedule, rather than only checking one.

The catalog could filter -- "show me everything that doesn't clash with what I
already have" -- but the actual question a student asks is the other way round:
*given these five courses I want and these hours I refuse, what are my options?*
Answering that is a search, not a filter.

Two things make it more than a nested loop:

**Sections are alternatives, not additions.** `MPCS 55001-1` and `MPCS 55001-2`
are the same Algorithms course at two different times. A schedule may contain
either, never both, and the solver has to try each in turn -- which is exactly
why enumeration beats filtering. Picking the section is most of the value.

**The space is too big to enumerate blindly.** Choosing 4 courses from a
164-section catalog is 29 million combinations. Two prunes do the work:

1. *Conflicts.* A partial schedule that already clashes cannot be rescued by
   adding to it, so the branch dies at depth 2 instead of depth 4.
2. *Cost.* Most surviving branches lead to schedules worse than ones already
   found. Every penalty except gaps only grows as courses are added, so a
   partial schedule's accumulated penalty is a valid lower bound on anything
   below it, and the branch can be cut the moment that bound reaches the cost
   of the worst schedule currently kept. Gaps are excluded from the bound
   because they are *not* monotone: inserting a class into an idle afternoon
   reduces total gap time by the length of the class.

Measured on a synthetic 164-section, 80-course catalog, best 4-course
schedule, no preferences:

    conflict pruning only          137 s
    + cost bound (exhaustive)       19 s   4.9M nodes, proven optimal
    + default 200k node budget     0.8 s   same cheapest cost, not proven

On the bundled 30-course catalog the whole search is 320 nodes. The bound
does not change the answer, only the work -- there is a test cross-checking
it against brute force.
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from itertools import pairwise

from .catalog import Catalog, Course
from .meeting import Day, format_time

#: Penalty weights, in "minutes of annoyance", so every component of the score
#: is in one unit and the total is interpretable rather than arbitrary.
MINUTES_PER_EXTRA_DAY = 60
MINUTES_PER_DAY_OFF_VIOLATION = 480
GAP_WEIGHT = 0.5

#: How far past `node_budget` the search will go while it still has no answer
#: at all, before giving up and reporting that it found none.
HARD_CEILING = 10

#: Refuse to search forever on a large catalog with loose constraints. Sized
#: to return in well under a second; `SearchResult.proven_optimal` says
#: whether the budget was enough to prove the answer.
DEFAULT_NODE_BUDGET = 200_000


@dataclass(frozen=True)
class Preferences:
    """What "better" means. Everything here is soft unless noted.

    Soft is the right default: a hard "no class before 10am" can make a
    schedule impossible and report nothing, which is less useful than being
    shown the 9:30 option with the cost spelled out.
    """

    no_earlier_than: int | None = None
    no_later_than: int | None = None
    days_off: frozenset[Day] = frozenset()
    #: Treat `days_off` as a hard constraint instead of a large penalty.
    require_days_off: bool = False
    preferred_instructors: frozenset[str] = frozenset()
    minimize_days: bool = True
    minimize_gaps: bool = True


@dataclass(frozen=True)
class ScheduleOption:
    """One conflict-free schedule and why it scored the way it did."""

    courses: tuple[Course, ...]
    cost: float
    breakdown: dict[str, float] = field(default_factory=dict)

    @property
    def days_used(self) -> tuple[Day, ...]:
        return tuple(sorted({m.day for c in self.courses for m in c.meetings}))

    @property
    def earliest_start(self) -> int | None:
        starts = [m.start for c in self.courses for m in c.meetings]
        return min(starts) if starts else None

    @property
    def latest_end(self) -> int | None:
        ends = [m.end for c in self.courses for m in c.meetings]
        return max(ends) if ends else None

    @property
    def gap_minutes(self) -> int:
        return _gap_minutes(self.courses)

    def render(self) -> str:
        lines = [f"  cost {self.cost:.0f}"]
        for day in self.days_used:
            slots = sorted(
                (m for c in self.courses for m in c.meetings if m.day is day),
                key=lambda m: m.start,
            )
            entries = ", ".join(
                f"{format_time(m.start)}-{format_time(m.end)} "
                f"{_course_for(self.courses, m).code}"
                for m in slots
            )
            lines.append(f"    {day.short}  {entries}")
        drivers = ", ".join(
            f"{k} {v:.0f}" for k, v in sorted(self.breakdown.items()) if v
        )
        lines.append(f"    why: {drivers or 'no penalties'}")
        return "\n".join(lines)


def _course_for(courses: Sequence[Course], meeting) -> Course:
    return next(c for c in courses if meeting in c.meetings)


def _gap_minutes(courses: Sequence[Course]) -> int:
    """Idle minutes between consecutive classes on the same day.

    Only *between* classes: time before the first and after the last is not a
    gap, it is the rest of the day.
    """
    total = 0
    by_day: dict[Day, list] = {}
    for course in courses:
        for meeting in course.meetings:
            by_day.setdefault(meeting.day, []).append(meeting)
    for meetings in by_day.values():
        ordered = sorted(meetings, key=lambda m: m.start)
        for before, after in pairwise(ordered):
            total += max(0, after.start - before.end)
    return total


def score(courses: Sequence[Course], prefs: Preferences) -> tuple[float, dict]:
    """Cost of a schedule in penalty minutes. Lower is better."""
    breakdown = {
        "too_early": 0.0,
        "too_late": 0.0,
        "day_off": 0.0,
        "extra_days": 0.0,
        "gaps": 0.0,
        "instructor": 0.0,
    }

    for course in courses:
        for meeting in course.meetings:
            if prefs.no_earlier_than is not None and meeting.start < prefs.no_earlier_than:
                breakdown["too_early"] += prefs.no_earlier_than - meeting.start
            if prefs.no_later_than is not None and meeting.end > prefs.no_later_than:
                breakdown["too_late"] += meeting.end - prefs.no_later_than
            if meeting.day in prefs.days_off:
                breakdown["day_off"] += MINUTES_PER_DAY_OFF_VIOLATION

    days = {m.day for c in courses for m in c.meetings}
    if prefs.minimize_days:
        breakdown["extra_days"] = float(len(days) * MINUTES_PER_EXTRA_DAY)
    if prefs.minimize_gaps:
        breakdown["gaps"] = _gap_minutes(courses) * GAP_WEIGHT
    if prefs.preferred_instructors:
        wanted = {name.lower() for name in prefs.preferred_instructors}
        misses = sum(
            1 for c in courses if not any(w in c.instructor.lower() for w in wanted)
        )
        breakdown["instructor"] = float(misses * MINUTES_PER_EXTRA_DAY)

    return sum(breakdown.values()), breakdown


@dataclass(frozen=True)
class SearchResult:
    """What the search found, and whether it finished.

    `proven_optimal` is the honest part. The search is an anytime algorithm:
    it always returns the best schedules it reached, and on a large catalog
    with loose preferences it can run out of node budget first. Returning the
    answer without saying which case you are in would be the bug -- "these are
    the 5 best" and "these are the 5 best I had time to find" are different
    claims.
    """

    options: list[ScheduleOption]
    nodes: int
    proven_optimal: bool


def monotone_penalty(course: Course, prefs: Preferences) -> float:
    """The part of a course's cost that adding more courses can only increase.

    This is the branch-and-bound lower bound. Gaps are deliberately absent: a
    later course can land inside an existing gap and shrink the total, so
    including gaps here would prune branches that are actually optimal.
    """
    total = 0.0
    for meeting in course.meetings:
        if prefs.no_earlier_than is not None and meeting.start < prefs.no_earlier_than:
            total += prefs.no_earlier_than - meeting.start
        if prefs.no_later_than is not None and meeting.end > prefs.no_later_than:
            total += meeting.end - prefs.no_later_than
        if meeting.day in prefs.days_off:
            total += MINUTES_PER_DAY_OFF_VIOLATION
    if prefs.preferred_instructors:
        wanted = {name.lower() for name in prefs.preferred_instructors}
        if not any(w in course.instructor.lower() for w in wanted):
            total += MINUTES_PER_EXTRA_DAY
    return total


def sections_by_course(courses: Iterable[Course]) -> dict[str, list[Course]]:
    """Group `MPCS 55001-1` and `MPCS 55001-2` under `MPCS 55001`."""
    groups: dict[str, list[Course]] = {}
    for course in courses:
        groups.setdefault(course.base_code, []).append(course)
    for sections in groups.values():
        sections.sort(key=lambda c: c.code)
    return groups


def solve(
    catalog: Catalog,
    size: int,
    *,
    required: Iterable[str] = (),
    among: Iterable[str] | None = None,
    preferences: Preferences | None = None,
    limit: int = 5,
    node_budget: int = DEFAULT_NODE_BUDGET,
) -> list[ScheduleOption]:
    """The best `limit` conflict-free schedules of `size` courses.

    Convenience wrapper over `search` for callers that do not care whether the
    result is proven optimal.
    """
    return search(
        catalog,
        size,
        required=required,
        among=among,
        preferences=preferences,
        limit=limit,
        node_budget=node_budget,
    ).options


def search(
    catalog: Catalog,
    size: int,
    *,
    required: Iterable[str] = (),
    among: Iterable[str] | None = None,
    preferences: Preferences | None = None,
    limit: int = 5,
    node_budget: int = DEFAULT_NODE_BUDGET,
) -> SearchResult:
    """The best `limit` conflict-free schedules of `size` courses.

    `required` names courses that must appear -- by base code (`MPCS 55001`,
    any section) or by exact section (`MPCS 55001-2`). `among` restricts the
    pool the rest are drawn from.
    """
    prefs = preferences or Preferences()
    if size <= 0:
        raise ValueError("size must be at least 1")

    all_sections = sections_by_course(catalog)
    pool = dict(all_sections)
    if among is not None:
        keys = {_normalise(code) for code in among}
        pool = {k: v for k, v in pool.items() if k in keys}

    fixed_groups: list[list[Course]] = []
    seen: set[str] = set()
    for code in required:
        key = _normalise(code)
        sections = all_sections.get(key)
        if sections is None:
            raise KeyError(f"no course matching {code!r}")
        if key in seen:
            # Two sections of one course are alternatives, not two courses.
            raise ValueError(f"{key} required twice")
        seen.add(key)
        exact = [c for c in sections if c.code == code.strip().upper()]
        fixed_groups.append(exact or sections)
        pool.pop(key, None)

    if len(fixed_groups) > size:
        raise ValueError(
            f"{len(fixed_groups)} required courses do not fit in a schedule of {size}"
        )

    if prefs.require_days_off:
        blocked = prefs.days_off
        pool = {
            key: [c for c in sections
                  if not any(m.day in blocked for m in c.meetings)]
            for key, sections in pool.items()
        }
        pool = {k: v for k, v in pool.items() if v}

    optional = [pool[k] for k in sorted(pool)]
    # Cheapest courses first, so a good schedule is found early and the bound
    # is tight for the rest of the search. Ordering does not change the answer,
    # only how much of the tree has to be visited to prove it.
    optional.sort(key=lambda g: min(monotone_penalty(c, prefs) for c in g))
    for group in optional:
        group.sort(key=lambda c: monotone_penalty(c, prefs))

    # Fixed courses first: a clash among them kills the branch at depth 0
    # instead of after every optional course has been enumerated.
    groups = fixed_groups + optional
    required_depth = len(fixed_groups)

    # A max-heap of the `limit` cheapest schedules, keyed by negated cost so
    # heap[0] is the worst one kept -- which is the bound to prune against.
    heap: list[tuple[float, tuple[str, ...], ScheduleOption]] = []
    chosen: list[Course] = []
    day_counts: dict[Day, int] = {}
    nodes = 0
    accumulated = 0.0
    exhausted = False

    # The most a single remaining course can shrink the gaps already present
    # (it can only fill idle time it fits into).
    longest_remaining = max(
        (
            sum(m.duration_minutes for m in c.meetings)
            for group in groups
            for c in group
        ),
        default=0,
    )

    def nonlocal_exhausted() -> None:
        nonlocal exhausted
        exhausted = True

    def keep(option: ScheduleOption) -> None:
        entry = (-option.cost, tuple(c.code for c in option.courses), option)
        if len(heap) < limit:
            heapq.heappush(heap, entry)
        else:
            heapq.heappushpop(heap, entry)

    def bound() -> float:
        """Lowest cost any schedule below this node could reach.

        Three admissible terms. `accumulated` is the monotone penalty of what
        is already chosen. Days can only be added, never removed. Gaps are the
        subtle one: adding a course can only shrink the current gap total, and
        only by as much as that course's own length -- so the gaps already
        present, less the most the remaining picks could fill, is a floor.
        """
        total = accumulated
        if prefs.minimize_days:
            total += len(day_counts) * MINUTES_PER_EXTRA_DAY
        if prefs.minimize_gaps:
            fillable = (size - len(chosen)) * longest_remaining
            total += max(0, _gap_minutes(chosen) - fillable) * GAP_WEIGHT
        return total

    def recurse(index: int) -> None:
        nonlocal nodes, accumulated

        if len(chosen) == size:
            total, breakdown = score(chosen, prefs)
            keep(ScheduleOption(tuple(chosen), total, breakdown))
            return
        # Not enough groups left to reach `size`: abandon the branch.
        if size - len(chosen) > len(groups) - index:
            return
        # The budget must not fire before there is anything to return: an
        # anytime algorithm that answers "nothing" is worse than a slow one.
        # Past a hard ceiling it gives up anyway, because the constraints may
        # simply be unsatisfiable and proving that can cost the whole tree.
        if nodes > node_budget and (heap or nodes > node_budget * HARD_CEILING):
            nonlocal_exhausted()
            return
        # Every remaining penalty except gaps only grows, so a bound already
        # at or above the worst kept schedule cannot be beaten below here.
        if len(heap) == limit and bound() >= -heap[0][0]:
            return

        for section in groups[index]:
            nodes += 1
            if any(section.conflicts_with(picked) for picked in chosen):
                continue
            chosen.append(section)
            accumulated += monotone_penalty(section, prefs)
            for meeting in section.meetings:
                day_counts[meeting.day] = day_counts.get(meeting.day, 0) + 1
            recurse(index + 1)
            for meeting in section.meetings:
                if day_counts[meeting.day] == 1:
                    del day_counts[meeting.day]
                else:
                    day_counts[meeting.day] -= 1
            accumulated -= monotone_penalty(section, prefs)
            chosen.pop()

        # A required course cannot be skipped; an optional one can.
        if index >= required_depth:
            recurse(index + 1)

    recurse(0)
    best = [entry[2] for entry in heap]
    best.sort(key=lambda o: (o.cost, tuple(c.code for c in o.courses)))
    return SearchResult(options=best, nodes=nodes, proven_optimal=not exhausted)


def _normalise(code: str) -> str:
    """'MPCS 55001-2' and 'mpcs 55001' both key to 'MPCS 55001'."""
    return code.strip().upper().split("-")[0].strip()
