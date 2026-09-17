# Earnings Drift Tracker

Measures **post-earnings-announcement drift** — the tendency of a stock to keep
moving in the direction of an earnings surprise for days after the announcement —
against the size of that surprise.

Earnings surprises come from Financial Modeling Prep; daily prices from Yahoo
Finance.

```
$ earnings-drift AAPL --start 2021-01-01 --end 2023-12-31
12 earnings events

event_date baseline_date  surprise_pct       1d       5d      10d
2021-01-27    2021-01-27         19.02  -0.0377  -0.0075   0.0105
...

Average post-earnings drift:
    1d  +0.42%
    5d  +1.18%
   10d  +1.63%

Surprise vs 1d return correlation: +0.284
```

## Install and run

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
export FMP_API_KEY=...          # free tier at financialmodelingprep.com
earnings-drift AAPL --plot
```

```bash
pytest -q        # 29 tests, no network
ruff check .
```

## How it works

```
sources.py   FMP earnings surprises + Yahoo daily closes      (network)
models.py    EarningsReport, Stock                            (types)
drift.py     baseline lookup, forward returns, correlation    (pure)
report.py    text summary and scatter plot                    (presentation)
cli.py       argument parsing                                 (entry point)
```

`drift.py` is pure: it takes a price frame and returns numbers. No network, no
printing, no plotting. That is what makes the arithmetic — the part that can be
silently wrong — directly testable.

## Measurement decisions

Three choices here change the answer, so they are stated rather than buried:

**Announcements that fall on a non-trading day use the prior session's close as
the baseline.** Earnings are routinely released after the close, on a holiday,
or over a weekend. Requiring an exact match against the price index drops those
events, and they are not a random subset.

**A horizon with insufficient history is omitted, not zero-filled.** A missing
10-day return on a recent announcement is unknown, not flat.

**A zero consensus estimate yields an undefined surprise percentage, not 0%.**
Putting a real surprise at the "no surprise" point on the x-axis biases the
correlation toward zero.

**Correlation needs at least three paired observations.** Over two points it is
always ±1 and carries no information.

## Notes

- Drift is measured in trading days from the baseline close, not calendar days.
- Prices are auto-adjusted for splits and dividends.
- The correlation is descriptive. It is not a strategy, and it is not corrected
  for market or sector moves over the same window.

## Changes from the first version

The original was five scripts sharing module-level state. This version fixes
four things that affected results or usability:

- `data_loader.py` called `input()` at import time, so importing anything in the
  project prompted for an API key. Credentials now come from `FMP_API_KEY`.
- Announcements not landing exactly on a trading day were silently skipped.
- Horizons past the end of the price history raised `IndexError` and dropped the
  whole event, rather than just the unmeasurable horizon.
- `show_drift_summary` mutated the DataFrame passed to it.
