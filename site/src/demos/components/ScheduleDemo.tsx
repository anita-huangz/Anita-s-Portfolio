import { useMemo, useState } from "react";

import data from "../../data/demos/courses.json";
import {
  type Course,
  DAY_NAMES,
  conflictsWith,
  formatTime,
  searchByCode,
  searchByKeyword,
} from "../lib/schedule";

const COURSES = data.courses as Course[];
const DAYS = [0, 1, 2, 3, 4];
const SEED_CODE = "MPCS 53112-1";

// The calendar window, derived from the data rather than assumed.
const EARLIEST = Math.min(...COURSES.flatMap((c) => c.meetings.map((m) => m.start)));
const LATEST = Math.max(...COURSES.flatMap((c) => c.meetings.map((m) => m.end)));

export function ScheduleDemo() {
  // Seeded with one course so the calendar shows something on open; an
  // empty grid reads as "broken" rather than "nothing added yet".
  const [enrolled, setEnrolled] = useState<Course[]>(() =>
    COURSES.filter((c) => c.code === SEED_CODE),
  );
  const [query, setQuery] = useState("");

  const results = useMemo(() => {
    const q = query.trim();
    if (!q) return COURSES;
    const byCode = searchByCode(COURSES, q);
    return byCode.length > 0 ? byCode : searchByKeyword(COURSES, q);
  }, [query]);

  const enrolledCodes = new Set(enrolled.map((c) => c.code));

  const toggle = (course: Course) => {
    setEnrolled((cur) =>
      cur.some((c) => c.code === course.code)
        ? cur.filter((c) => c.code !== course.code)
        : [...cur, course],
    );
  };

  const span = LATEST - EARLIEST;
  const rowFor = (start: number, end: number) => ({
    top: `${((start - EARLIEST) / span) * 100}%`,
    height: `${((end - start) / span) * 100}%`,
  });

  // Clashes within the enrolled set, for the calendar's red blocks.
  const clashing = new Set<string>();
  for (const course of enrolled) {
    if (conflictsWith(course, enrolled).length > 0) clashing.add(course.code);
  }

  return (
    <div className="demo">
      <div className="demo-controls">
        <label className="control" style={{ flex: 1 }}>
          <span className="control-label">Search</span>
          <input
            className="demo-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="code prefix (MPCS 511, or 530) or a keyword (algorithms, Adams)"
            spellCheck={false}
          />
        </label>
        {enrolled.length > 0 && (
          <button className="chip" onClick={() => setEnrolled([])}>
            Clear {enrolled.length}
          </button>
        )}
      </div>

      <div className="demo-split schedule-split">
        <div className="course-list">
          <h5 className="demo-h">{results.length} course(s)</h5>
          {results.map((course) => {
            const clashes = conflictsWith(course, enrolled);
            const isOn = enrolledCodes.has(course.code);
            return (
              <button
                key={course.code}
                className={`course-row${isOn ? " on" : ""}${
                  !isOn && clashes.length ? " blocked" : ""
                }`}
                onClick={() => toggle(course)}
              >
                <span className="course-code">{course.code}</span>
                <span className="course-name">{course.name}</span>
                <span className="course-when">
                  {course.meetings
                    .map((m) => `${DAY_NAMES[m.day].slice(0, 3)} ${formatTime(m.start)}`)
                    .join(", ") || "unscheduled"}
                </span>
                {!isOn && clashes.length > 0 && (
                  <span className="course-clash">clashes with {clashes[0].code}</span>
                )}
              </button>
            );
          })}
        </div>

        <div>
          <h5 className="demo-h">Your week</h5>
          <div className="calendar">
            {DAYS.map((day) => (
              <div className="cal-day" key={day}>
                <div className="cal-head">{DAY_NAMES[day].slice(0, 3)}</div>
                <div className="cal-col">
                  {enrolled.flatMap((course) =>
                    course.meetings
                      .filter((m) => m.day === day)
                      .map((m, i) => (
                        <div
                          key={`${course.code}-${i}`}
                          className={`cal-block${clashing.has(course.code) ? " clash" : ""}`}
                          style={rowFor(m.start, m.end)}
                          title={`${course.code} ${formatTime(m.start)}-${formatTime(m.end)}`}
                        >
                          <span>{course.code.replace("MPCS ", "")}</span>
                        </div>
                      )),
                  )}
                </div>
              </div>
            ))}
          </div>
          <p className="demo-note" style={{ marginTop: 12 }}>
            Add courses from the list. Anything that would overlap what you already have
            is marked in the list before you click it; a genuine clash turns red on the
            calendar. Meetings are half-open intervals, so a class ending at 19:30 and
            one starting at 19:30 are back to back, not a conflict.
          </p>
        </div>
      </div>
    </div>
  );
}
