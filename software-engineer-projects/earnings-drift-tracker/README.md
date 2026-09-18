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
pytest -q        # 47 tests, no network
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

## One correlation is the wrong summary

The headline above is a single ticker's correlation, and across a real sample
that number is close to useless. Pooled over **2,388 announcements from 62
companies** — the sample the site's demo runs on — the surprise-to-drift
correlation is `+0.038` at one day, `+0.011` at five, and `-0.003` at ten.
Read on its own, that says there is no effect.

Sorted into surprise quintiles, the same events say something different:

```
horizon 5d                n    mean surprise    mean drift        t
  Q1 (most negative)    479          -50.50%       -0.48%    -1.53
  Q2                    476           +1.98%       +0.27%    +1.11
  Q3                    478           +4.88%       +0.30%    +1.21
  Q4                    478          +10.23%       +0.91%    +3.46  *
  Q5 (most positive)    477          +63.03%       +1.10%    +3.24  *

  top minus bottom   +1.57%   t = 3.42   monotonic   significant
  hit rate 53.5%
```

The relationship is there and it is ordered — drift rises across every
quintile — but it is not linear, so a Pearson correlation averages it away.
That is why `surprise_buckets()` and `spread_test()` exist and why the
long-short spread, not the correlation, is the number to read. The spread is
significant at all three horizons (t = 4.29, 3.42, 3.21) and monotonic at one
and five days but **not** at ten, which is the kind of detail a correlation
cannot express either way.

Two cautions that keep this honest. The hit rate is 52–55% against a coin
flip's 50%, so the effect is real and small — the spread comes from the size of
the moves, not from being right more often. And the quintile breakpoints are
wildly uneven: Q1 averages a −50% surprise while Q2 averages +2%, because
consensus estimates cluster just below what companies report. Equal-count
buckets are not equal-width ones.

The table above is cross-sectional, and the command line is single-ticker —
quintiles of a dozen events say nothing. Pool first:

```python
from earnings_drift.drift import analyze_drift, pool, spread_test, surprise_buckets

drift = pool(analyze_drift(stock, benchmark=spy) for stock in stocks)
for bucket in surprise_buckets(drift, horizon=5):
    print(bucket.label, bucket.n, bucket.mean_return, bucket.t_stat)
print(spread_test(drift, horizon=5))
```

## Notes

- Drift is measured in trading days from the baseline close, not calendar days.
- Prices are auto-adjusted for splits and dividends.
- Pass a benchmark and every horizon also gets an **abnormal** return — the
  stock's move minus the benchmark's over the identical window. A stock that
  rose 4% in a week the whole market rose 4% has not drifted, and the bucket
  and spread tests default to the abnormal column when one is available. The
  quintile table above is raw returns, because the committed extract it was
  computed from does not carry the benchmark column.
- `run_up` records the move over the sessions *before* the announcement, so a
  price that had already absorbed the news is visible rather than counted as
  drift.
- None of this is a strategy. There is no position sizing, no cost model, and
  no attempt to trade the spread.

## Changes from the first version

The original was five scripts sharing module-level state. This version fixes
four things that affected results or usability:

- `data_loader.py` called `input()` at import time, so importing anything in the
  project prompted for an API key. Credentials now come from `FMP_API_KEY`.
- Announcements not landing exactly on a trading day were silently skipped.
- Horizons past the end of the price history raised `IndexError` and dropped the
  whole event, rather than just the unmeasurable horizon.
- `show_drift_summary` mutated the DataFrame passed to it.
