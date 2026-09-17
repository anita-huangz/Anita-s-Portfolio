# Course Catalog & Scheduling

Search a university course catalog and build a schedule that doesn't
double-book you. Ships with the MPCS catalog as sample data.

```
$ course-catalog --schedule "MPCS 53112-1" --code "MPCS 530"
Enrolled (1):
  MPCS 53112-1: Advanced Data Analytics (Wed 17:30-20:30)

2 course(s) — code ~ 'MPCS 530':
  MPCS 53014-1: Big Data Application Architecture (Mon 17:30-20:30)
  MPCS 53001-1: Databases (Tue 17:30-20:30)
```

Anything overlapping what you're already enrolled in is filtered out.

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"

course-catalog                                   # everything
course-catalog --code "MPCS 511"                 # code prefix
course-catalog --keyword algorithms              # title or instructor
course-catalog --day tuesday                     # by day
course-catalog --schedule "MPCS 51040-1" --free  # what still fits

pytest -q       # 52 tests
ruff check .
```

## Layout

```
src/course_catalog/
  meeting.py   Day, Meeting, time parsing, overlap   (pure)
  catalog.py   Course, Catalog, search, scheduling   (pure)
  cli.py       argument parsing and output
  data/        the bundled catalog CSV
```

## Modelling decision

A meeting is a day plus a **half-open** minute interval `[start, end)`. That's
the whole conflict rule:

```python
self.start < other.end and other.start < self.end
```

Half-open matters. A class ending at 7:30pm and another starting at 7:30pm are
back to back, not a conflict — a closed interval would reject a perfectly valid
schedule. There's a test for exactly that pair.

Times are stored as minutes since midnight, so 12:00am → 0 and 12:00pm → 720.
Those two are the cases that break naive AM/PM arithmetic, and both are tested.

## Bugs this version fixes

**Prefix search was actually substring search.**

```python
matched = [c for c in courses if prefix in c.code]   # substring
```

The docstring promised "code starts with the given prefix". Searching `"530"`
matched `MPCS 53014-1` — but via the digits in the *middle* of the number, not
the start. Every result looked plausible, which is why it went unnoticed.
Matching is now a real prefix test against the full code *and* the bare number,
so both `"MPCS 530"` and `"530"` work.

**The default data path could never load.**

```python
def __init__(self, filename="data/courses.csv"):
    file_path = Path(__file__).parent / filename
```

`__file__` was `notebooks/catalog.py`, so this resolved to
`notebooks/data/courses.csv` — but `data/` was a sibling of `notebooks/`, not a
child. The default always raised. The CSV is now packaged and read through
`importlib.resources`, so it resolves from an installed wheel too.

**`main.py` hardcoded an absolute path** to
`/Users/anitahuang/anita-huangz.github.io/software-engineer-projects/Course Catalog and Scheduling System/data/courses.csv`
— a directory that no longer exists, on one specific machine.

Also fixed:

- Malformed times parsed into plausible-looking numbers instead of raising, so
  a typo in the catalog silently misplaced a class. Times now validate, and a
  bad row reports its line number.
- A course already in your schedule was offered back to you as an option — it
  conflicts with itself.
- A meeting ending before it starts was accepted.
- `build_schedule` now rejects unknown codes rather than dropping them; a
  schedule that silently ignored a typo would look conflict-free for the wrong
  reason.

## Notes

- Day names accept `Mon`, `Monday`, or `MONDAYS`.
- Multiple meetings per course are separated by `;` and conflict independently
  — a Tue/Thu course clashes with anything on either day.
- A course with an empty meeting-times field is kept and reported as
  `unscheduled`; it conflicts with nothing.
