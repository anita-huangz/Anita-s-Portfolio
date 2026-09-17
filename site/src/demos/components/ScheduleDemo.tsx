import { useMemo, useState } from "react";

import data from "../../data/demos/courses.json";
import {
  type Course,
  type ScheduleOption,
  DAY_NAMES,
  conflictsWith,
  daysUsed,
  formatTime,
  gapMinutes,
  searchByCode,
  searchByKeyword,
  searchSchedules,
  sectionsByCourse,
} from "../lib/schedule";
import { Term } from "./Term";

const COURSES = data.courses as Course[];
const DAYS = [0, 1, 2, 3, 4];
const SEED_CODE = "MPCS 53112-1";

// The calendar window, derived from the data rather than assumed.
const EARLIEST = Math.min(...COURSES.flatMap((c) => c.meetings.map((m) => m.start)));
const LATEST = Math.max(...COURSES.flatMap((c) => c.meetings.map((m) => m.end)));

const BASE_CODES = [...sectionsByCourse(COURSES).keys()].sort();

/** Labels for the score breakdown, so `extra_days` reads as something. */
const PENALTY_LABELS: Record<string, string> = {
  too_early: "too early",
  too_late: "too late",
  day_off: "day off",
  extra_days: "days on campus",
  gaps: "gaps",
  instructor: "instructor",
};

function drivers(option: ScheduleOption): string {
  const parts = Object.entries(option.breakdown)
    .filter(([, v]) => v > 0)
    .sort((a, b) => b[1] - a[1])
    .map(([k, v]) => `${PENALTY_LABELS[k] ?? k} ${Math.round(v)}`);
  return parts.length > 0 ? parts.join(" · ") : "no penalties";
}

export function ScheduleDemo() {
  // Seeded with one course so the calendar shows something on open; an
  // empty grid reads as "broken" rather than "nothing added yet".
  const [enrolled, setEnrolled] = useState<Course[]>(() =>
    COURSES.filter((c) => c.code === SEED_CODE),
  );
  const [query, setQuery] = useState("");

  // Solver controls.
  // null turns the solver off, so Reset falls back to the hand-built view
  // rather than asking for a schedule of zero courses.
  const [size, setSize] = useState<number | null>(3);
  const [required, setRequired] = useState<string[]>([]);
  const [daysOff, setDaysOff] = useState<number[]>([]);
  const [strictDaysOff, setStrictDaysOff] = useState(false);
  const [noEarlierThan, setNoEarlierThan] = useState<number | null>(null);
  const [picked, setPicked] = useState(0);

  const solved = useMemo(() => {
    if (size === null) return { options: [], nodes: 0, provenOptimal: true };
    try {
      return searchSchedules(COURSES, size, {
        required,
        preferences: {
          daysOff,
          requireDaysOff: strictDaysOff,
          noEarlierThan,
        },
        limit: 4,
      });
    } catch (err) {
      return { options: [], nodes: 0, provenOptimal: true, error: String(err) };
    }
  }, [size, required, daysOff, strictDaysOff, noEarlierThan]);

  const chosen = solved.options[Math.min(picked, solved.options.length - 1)];

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

  // The calendar shows the solver's pick when there is one, and the
  // hand-built schedule otherwise.
  const shown = chosen ? chosen.courses : enrolled;

  const span = LATEST - EARLIEST;
  const rowFor = (start: number, end: number) => ({
    top: `${((start - EARLIEST) / span) * 100}%`,
    height: `${((end - start) / span) * 100}%`,
  });

  // Clashes within whatever is on the calendar, for the red blocks. A solved
  // schedule never has any, which is the point -- the marker is there for the
  // hand-built case.
  const clashing = new Set<string>();
  for (const course of shown) {
    if (conflictsWith(course, shown).length > 0) clashing.add(course.code);
  }

  const toggleRequired = (code: string) => {
    setPicked(0);
    setRequired((cur) =>
      cur.includes(code) ? cur.filter((c) => c !== code) : [...cur, code],
    );
  };

  const toggleDayOff = (day: number) => {
    setPicked(0);
    setDaysOff((cur) =>
      cur.includes(day) ? cur.filter((d) => d !== day) : [...cur, day],
    );
  };

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
        {(enrolled.length > 0 || solved.options.length > 0) && (
          <button
            className="chip"
            onClick={() => {
              setEnrolled([]);
              setSize(null);
              setRequired([]);
              setDaysOff([]);
              setPicked(0);
            }}
          >
            Reset
          </button>
        )}
      </div>

      <div className="solver-panel">
        <div className="demo-controls">
          <label className="control">
            <span className="control-label">Build</span>
            {[2, 3, 4, 5].map((n) => (
              <button
                key={n}
                className="chip mono"
                aria-pressed={size === n}
                onClick={() => {
                  setSize(n);
                  setPicked(0);
                }}
              >
                {n}
              </button>
            ))}
            <span className="demo-hint">courses</span>
          </label>

          <label className="control">
            <span className="control-label">Nothing before</span>
            {[
              { label: "any", value: null },
              { label: "10am", value: 600 },
              { label: "2pm", value: 840 },
              { label: "5pm", value: 1020 },
            ].map((opt) => (
              <button
                key={opt.label}
                className="chip"
                aria-pressed={noEarlierThan === opt.value}
                onClick={() => {
                  setNoEarlierThan(opt.value);
                  setPicked(0);
                }}
              >
                {opt.label}
              </button>
            ))}
          </label>

          <label className="control">
            <span className="control-label">Keep free</span>
            {DAYS.map((day) => (
              <button
                key={day}
                className="chip"
                aria-pressed={daysOff.includes(day)}
                onClick={() => toggleDayOff(day)}
              >
                {DAY_NAMES[day].slice(0, 3)}
              </button>
            ))}
            {daysOff.length > 0 && (
              <button
                className="chip"
                aria-pressed={strictDaysOff}
                onClick={() => {
                  setStrictDaysOff((v) => !v);
                  setPicked(0);
                }}
                title="Treat the days off as a hard constraint rather than a penalty"
              >
                strict
              </button>
            )}
          </label>
        </div>

        <div className="demo-controls">
          <label className="control" style={{ alignItems: "flex-start" }}>
            <span className="control-label">Must include</span>
            <span className="chip-wrap">
              {BASE_CODES.map((code) => (
                <button
                  key={code}
                  className="chip mono"
                  aria-pressed={required.includes(code)}
                  onClick={() => toggleRequired(code)}
                >
                  {code.replace("MPCS ", "")}
                </button>
              ))}
            </span>
          </label>
        </div>

        {"error" in solved && solved.error ? (
          <p className="demo-note">
            {String(solved.error).replace("Error: ", "")}
          </p>
        ) : size === null ? (
          <p className="demo-note">
            Pick a size to have the solver build a schedule, or add courses by
            hand from the list below.
          </p>
        ) : solved.options.length === 0 ? (
          <p className="demo-note">
            No conflict-free schedule of {size} fits those constraints. Drop a
            requirement or free up a day.
          </p>
        ) : (
          <>
            <p className="demo-hint" style={{ margin: "12px 0 0" }}>
              Each option is one <Term id="conflict">conflict</Term>-free week.
              Lower <Term id="cost" /> is better, and a <Term id="section" /> is
              picked for you.
            </p>
            <div className="option-row">
              {solved.options.map((option, i) => (
                <button
                  key={option.courses.map((c) => c.code).join()}
                  className={`option-card${i === Math.min(picked, solved.options.length - 1) ? " on" : ""}`}
                  onClick={() => setPicked(i)}
                >
                  <span className="option-cost">
                    cost {Math.round(option.cost)}
                  </span>
                  <span className="option-codes">
                    {option.courses
                      .map((c) => c.code.replace("MPCS ", ""))
                      .join(" · ")}
                  </span>
                  <span className="option-why">
                    {daysUsed(option).length} day
                    {daysUsed(option).length === 1 ? "" : "s"},{" "}
                    {gapMinutes(option.courses)} min idle
                  </span>
                </button>
              ))}
            </div>
            {chosen && (
              <p className="demo-note">
                Scored in <strong>minutes of annoyance</strong>, so the total is
                interpretable rather than an arbitrary weighted sum:{" "}
                {drivers(chosen)}. Searched{" "}
                <Term id="proven-optimal">
                  {solved.nodes.toLocaleString()} nodes
                </Term>
                {solved.provenOptimal
                  ? " and proved this is the best there is."
                  : ", then ran out of budget — so this is the best found, not provably the best."}
              </p>
            )}
          </>
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
          <h5 className="demo-h">
            {chosen ? "The solver's week" : "Your week"}
          </h5>
          <div className="calendar">
            {DAYS.map((day) => (
              <div className="cal-day" key={day}>
                <div className="cal-head">{DAY_NAMES[day].slice(0, 3)}</div>
                <div className="cal-col">
                  {shown.flatMap((course) =>
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
            {chosen ? (
              <>
                Sections are alternatives, not additions: <code>55001-1</code> and{" "}
                <code>55001-2</code> are the same Algorithms course at two times, so
                the search picks one — which is the part no filter over the
                catalogue can do.
              </>
            ) : (
              <>
                Add courses from the list. Anything that would overlap what you already
                have is marked before you click it; a genuine clash turns red.
              </>
            )}{" "}
            Meetings are half-open intervals, so a class ending at 19:30 and one
            starting at 19:30 are back to back, not a conflict.
          </p>
        </div>
      </div>
    </div>
  );
}
