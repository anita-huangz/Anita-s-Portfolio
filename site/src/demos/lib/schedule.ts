/**
 * Port of `course_catalog` conflict logic, for the interactive timetable.
 * Checked in `schedule.test.ts` against every course pair's verdict from the
 * Python.
 */

export const DAY_NAMES = [
  "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday",
] as const;

export interface Meeting {
  /** 0 = Monday. */
  day: number;
  /** Minutes since midnight. */
  start: number;
  end: number;
}

export interface Course {
  code: string;
  name: string;
  instructor: string;
  location: string;
  meetings: Meeting[];
}

export function formatTime(minutes: number): string {
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

/**
 * Half-open intervals: a class ending at 19:30 and one starting at 19:30 are
 * back to back, not a conflict. A closed interval would reject a valid
 * schedule, and that distinction is the whole rule.
 */
export function meetingsOverlap(a: Meeting, b: Meeting): boolean {
  if (a.day !== b.day) return false;
  return a.start < b.end && b.start < a.end;
}

export function coursesConflict(a: Course, b: Course): boolean {
  return a.meetings.some((x) => b.meetings.some((y) => meetingsOverlap(x, y)));
}

/** Courses that fit alongside everything already scheduled. */
export function withoutConflicts(all: Course[], schedule: Course[]): Course[] {
  const booked = new Set(schedule.map((c) => c.code));
  return all.filter(
    (c) => !booked.has(c.code) && !schedule.some((s) => coursesConflict(c, s)),
  );
}

/** Which already-scheduled courses a candidate clashes with. */
export function conflictsWith(candidate: Course, schedule: Course[]): Course[] {
  return schedule.filter((s) => s.code !== candidate.code && coursesConflict(candidate, s));
}

export function subjectOf(course: Course): string {
  return course.code.split(" ")[0] ?? "";
}

export function numberOf(course: Course): string {
  const parts = course.code.split(/\s+/);
  return parts.slice(1).join(" ");
}

/** Prefix match against the full code or the bare number, case-insensitive. */
export function searchByCode(all: Course[], prefix: string): Course[] {
  const needle = prefix.trim().toLowerCase();
  if (!needle) return [];
  return all.filter(
    (c) =>
      c.code.toLowerCase().startsWith(needle) ||
      numberOf(c).toLowerCase().startsWith(needle),
  );
}

export function searchByKeyword(all: Course[], keyword: string): Course[] {
  const needle = keyword.trim().toLowerCase();
  if (!needle) return [];
  return all.filter(
    (c) =>
      c.name.toLowerCase().includes(needle) ||
      c.instructor.toLowerCase().includes(needle),
  );
}

// ---------------------------------------------------------------------------
// The solver — port of `course_catalog.solver`
// ---------------------------------------------------------------------------
//
// Filtering answers "what still fits?" The question a student asks is the
// reverse: given these courses I need and these hours I refuse, what are my
// options? That is a search, not a filter — and two things make it more than a
// nested loop.
//
// Sections are alternatives, not additions: `MPCS 55001-1` and `MPCS 55001-2`
// are the same course at two different times, so a schedule holds either and
// never both. Picking the section is most of the value, because no filter over
// the catalogue can do it.
//
// And the space is too big to walk. Choosing 4 from 164 sections is 29 million
// combinations, so the search prunes on conflicts (a partial schedule that
// already clashes cannot be rescued) and on cost (every penalty except gaps
// only grows, so the accumulated penalty bounds everything below a node).

/** Penalty weights, in "minutes of annoyance", so the total is interpretable. */
export const MINUTES_PER_EXTRA_DAY = 60;
export const MINUTES_PER_DAY_OFF_VIOLATION = 480;
export const GAP_WEIGHT = 0.5;

/** Keeps the browser responsive; `provenOptimal` reports when it bit. */
export const DEFAULT_NODE_BUDGET = 200_000;
const HARD_CEILING = 10;

export interface Preferences {
  noEarlierThan?: number | null;
  noLaterThan?: number | null;
  daysOff?: number[];
  requireDaysOff?: boolean;
  preferredInstructors?: string[];
  minimizeDays?: boolean;
  minimizeGaps?: boolean;
}

export interface ScoreBreakdown {
  too_early: number;
  too_late: number;
  day_off: number;
  extra_days: number;
  gaps: number;
  instructor: number;
}

export interface ScheduleOption {
  courses: Course[];
  cost: number;
  breakdown: ScoreBreakdown;
}

export interface SearchResult {
  options: ScheduleOption[];
  nodes: number;
  provenOptimal: boolean;
}

function prefs(p: Preferences) {
  return {
    noEarlierThan: p.noEarlierThan ?? null,
    noLaterThan: p.noLaterThan ?? null,
    daysOff: new Set(p.daysOff ?? []),
    requireDaysOff: p.requireDaysOff ?? false,
    preferredInstructors: (p.preferredInstructors ?? []).map((n) =>
      n.toLowerCase(),
    ),
    minimizeDays: p.minimizeDays ?? true,
    minimizeGaps: p.minimizeGaps ?? true,
  };
}

type Resolved = ReturnType<typeof prefs>;

/** `MPCS 55001` from `MPCS 55001-2`. */
export function baseCode(course: Course): string {
  return course.code.split("-")[0].trim();
}

/** `2` from `MPCS 55001-2`, or "" when the code carries no section. */
export function sectionOf(course: Course): string {
  const parts = course.code.split("-");
  return parts.length > 1 ? parts.slice(1).join("-").trim() : "";
}

export function normaliseCode(code: string): string {
  return code.trim().toUpperCase().split("-")[0].trim();
}

/** Group the sections of each course under its base code. */
export function sectionsByCourse(all: Course[]): Map<string, Course[]> {
  const groups = new Map<string, Course[]>();
  for (const course of all) {
    const key = baseCode(course);
    const list = groups.get(key);
    if (list) list.push(course);
    else groups.set(key, [course]);
  }
  for (const list of groups.values()) {
    list.sort((a, b) => (a.code < b.code ? -1 : a.code > b.code ? 1 : 0));
  }
  return groups;
}

/**
 * Idle minutes between consecutive classes on the same day.
 *
 * Only *between*: time before the first class and after the last is not a
 * gap, it is the rest of the day.
 */
export function gapMinutes(courses: Course[]): number {
  const byDay = new Map<number, Meeting[]>();
  for (const course of courses) {
    for (const meeting of course.meetings) {
      const list = byDay.get(meeting.day);
      if (list) list.push(meeting);
      else byDay.set(meeting.day, [meeting]);
    }
  }
  let total = 0;
  for (const meetings of byDay.values()) {
    const ordered = [...meetings].sort((a, b) => a.start - b.start);
    for (let i = 1; i < ordered.length; i++) {
      total += Math.max(0, ordered[i].start - ordered[i - 1].end);
    }
  }
  return total;
}

/** Cost of a schedule in penalty minutes. Lower is better. */
export function scoreSchedule(
  courses: Course[],
  preferences: Preferences = {},
): { cost: number; breakdown: ScoreBreakdown } {
  const p = prefs(preferences);
  const breakdown: ScoreBreakdown = {
    too_early: 0,
    too_late: 0,
    day_off: 0,
    extra_days: 0,
    gaps: 0,
    instructor: 0,
  };

  for (const course of courses) {
    for (const meeting of course.meetings) {
      if (p.noEarlierThan !== null && meeting.start < p.noEarlierThan) {
        breakdown.too_early += p.noEarlierThan - meeting.start;
      }
      if (p.noLaterThan !== null && meeting.end > p.noLaterThan) {
        breakdown.too_late += meeting.end - p.noLaterThan;
      }
      if (p.daysOff.has(meeting.day)) {
        breakdown.day_off += MINUTES_PER_DAY_OFF_VIOLATION;
      }
    }
  }

  const days = new Set(courses.flatMap((c) => c.meetings.map((m) => m.day)));
  if (p.minimizeDays) breakdown.extra_days = days.size * MINUTES_PER_EXTRA_DAY;
  if (p.minimizeGaps) breakdown.gaps = gapMinutes(courses) * GAP_WEIGHT;
  if (p.preferredInstructors.length > 0) {
    const misses = courses.filter(
      (c) =>
        !p.preferredInstructors.some((w) => c.instructor.toLowerCase().includes(w)),
    ).length;
    breakdown.instructor = misses * MINUTES_PER_EXTRA_DAY;
  }

  const cost = Object.values(breakdown).reduce((a, b) => a + b, 0);
  return { cost, breakdown };
}

/**
 * The part of a course's cost that adding more courses can only increase.
 *
 * This is the branch-and-bound lower bound. Gaps are deliberately absent: a
 * later course can land inside an existing gap and shrink the total, so
 * including gaps here would prune branches that are actually optimal.
 */
function monotonePenalty(course: Course, p: Resolved): number {
  let total = 0;
  for (const meeting of course.meetings) {
    if (p.noEarlierThan !== null && meeting.start < p.noEarlierThan) {
      total += p.noEarlierThan - meeting.start;
    }
    if (p.noLaterThan !== null && meeting.end > p.noLaterThan) {
      total += meeting.end - p.noLaterThan;
    }
    if (p.daysOff.has(meeting.day)) total += MINUTES_PER_DAY_OFF_VIOLATION;
  }
  if (
    p.preferredInstructors.length > 0 &&
    !p.preferredInstructors.some((w) => course.instructor.toLowerCase().includes(w))
  ) {
    total += MINUTES_PER_EXTRA_DAY;
  }
  return total;
}

export interface SolveOptions {
  required?: string[];
  among?: string[] | null;
  preferences?: Preferences;
  limit?: number;
  nodeBudget?: number;
}

/**
 * The best `limit` conflict-free schedules of `size` courses.
 *
 * Returns whether the answer is proven optimal rather than passing off "best
 * I had time to find" as "best" — the search is an anytime algorithm, and on a
 * large catalogue with loose preferences it can run out of budget first.
 */
export function searchSchedules(
  all: Course[],
  size: number,
  options: SolveOptions = {},
): SearchResult {
  if (size <= 0) throw new Error("size must be at least 1");

  const p = prefs(options.preferences ?? {});
  const limit = options.limit ?? 5;
  const nodeBudget = options.nodeBudget ?? DEFAULT_NODE_BUDGET;
  const allSections = sectionsByCourse(all);

  let pool = new Map(allSections);
  if (options.among) {
    const keys = new Set(options.among.map(normaliseCode));
    pool = new Map([...pool].filter(([key]) => keys.has(key)));
  }

  const fixedGroups: Course[][] = [];
  const seen = new Set<string>();
  for (const code of options.required ?? []) {
    const key = normaliseCode(code);
    const sections = allSections.get(key);
    if (!sections) throw new Error(`no course matching ${code}`);
    if (seen.has(key)) throw new Error(`${key} required twice`);
    seen.add(key);
    const exact = sections.filter((c) => c.code === code.trim().toUpperCase());
    fixedGroups.push(exact.length > 0 ? exact : sections);
    pool.delete(key);
  }

  if (fixedGroups.length > size) {
    throw new Error(
      `${fixedGroups.length} required courses do not fit in a schedule of ${size}`,
    );
  }

  if (p.requireDaysOff) {
    pool = new Map(
      [...pool]
        .map(
          ([key, sections]) =>
            [
              key,
              sections.filter((c) => !c.meetings.some((m) => p.daysOff.has(m.day))),
            ] as [string, Course[]],
        )
        .filter(([, sections]) => sections.length > 0),
    );
  }

  const optional = [...pool.keys()].sort().map((k) => pool.get(k)!);
  // Cheapest first, so a good schedule is found early and the bound is tight
  // for the rest of the search. Ordering changes the work, not the answer.
  for (const group of optional) {
    group.sort((a, b) => monotonePenalty(a, p) - monotonePenalty(b, p));
  }
  optional.sort(
    (a, b) =>
      Math.min(...a.map((c) => monotonePenalty(c, p))) -
      Math.min(...b.map((c) => monotonePenalty(c, p))),
  );

  const groups = [...fixedGroups, ...optional];
  const requiredDepth = fixedGroups.length;
  const longestRemaining = Math.max(
    0,
    ...groups.flatMap((g) =>
      g.map((c) => c.meetings.reduce((sum, m) => sum + (m.end - m.start), 0)),
    ),
  );

  const kept: ScheduleOption[] = [];
  const chosen: Course[] = [];
  const dayCounts = new Map<number, number>();
  let nodes = 0;
  let accumulated = 0;
  let exhausted = false;

  /** Worst cost currently kept — the value to prune against. */
  const worstKept = () =>
    kept.length < limit ? Infinity : kept[kept.length - 1].cost;

  function keep(option: ScheduleOption): void {
    // A short sorted list rather than a heap, matching the Python: a heap's
    // tie-breaking runs backwards, discarding the alphabetically first of
    // several equal-cost options. `limit` is single digits, so an insertion
    // into a short list is both cheaper and deterministic in the same order
    // the results are finally reported in.
    const codes = option.courses.map((c) => c.code).join(",");
    let i = kept.findIndex(
      (o) =>
        o.cost > option.cost ||
        (o.cost === option.cost && o.courses.map((c) => c.code).join(",") > codes),
    );
    if (i === -1) i = kept.length;
    kept.splice(i, 0, option);
    if (kept.length > limit) kept.pop();
  }

  function bound(): number {
    let total = accumulated;
    if (p.minimizeDays) total += dayCounts.size * MINUTES_PER_EXTRA_DAY;
    if (p.minimizeGaps) {
      const fillable = (size - chosen.length) * longestRemaining;
      total += Math.max(0, gapMinutes(chosen) - fillable) * GAP_WEIGHT;
    }
    return total;
  }

  function conflictsWithChosen(course: Course): boolean {
    return chosen.some((picked) => coursesConflict(picked, course));
  }

  function recurse(index: number): void {
    if (chosen.length === size) {
      const { cost, breakdown } = scoreSchedule(chosen, options.preferences ?? {});
      keep({ courses: [...chosen], cost, breakdown });
      return;
    }
    if (size - chosen.length > groups.length - index) return;
    // The budget must not fire before there is anything to return: an anytime
    // algorithm that answers "nothing" is worse than a slow one. Past a hard
    // ceiling it gives up anyway, since the constraints may be unsatisfiable.
    if (
      nodes > nodeBudget &&
      (kept.length > 0 || nodes > nodeBudget * HARD_CEILING)
    ) {
      exhausted = true;
      return;
    }
    if (kept.length === limit && bound() >= worstKept()) return;

    for (const section of groups[index]) {
      nodes += 1;
      if (conflictsWithChosen(section)) continue;
      chosen.push(section);
      accumulated += monotonePenalty(section, p);
      for (const meeting of section.meetings) {
        dayCounts.set(meeting.day, (dayCounts.get(meeting.day) ?? 0) + 1);
      }
      recurse(index + 1);
      for (const meeting of section.meetings) {
        const n = dayCounts.get(meeting.day)!;
        if (n === 1) dayCounts.delete(meeting.day);
        else dayCounts.set(meeting.day, n - 1);
      }
      accumulated -= monotonePenalty(section, p);
      chosen.pop();
    }

    // A required course cannot be skipped; an optional one can.
    if (index >= requiredDepth) recurse(index + 1);
  }

  recurse(0);
  // Already in (cost, codes) order by construction.
  return { options: kept, nodes, provenOptimal: !exhausted };
}

export function solveSchedules(
  all: Course[],
  size: number,
  options: SolveOptions = {},
): ScheduleOption[] {
  return searchSchedules(all, size, options).options;
}

export function daysUsed(option: ScheduleOption): number[] {
  return [
    ...new Set(option.courses.flatMap((c) => c.meetings.map((m) => m.day))),
  ].sort((a, b) => a - b);
}
