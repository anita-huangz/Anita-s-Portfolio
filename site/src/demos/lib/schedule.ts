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
