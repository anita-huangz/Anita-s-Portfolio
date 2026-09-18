# Demo data generators

Each script runs a project's own package against its real source and writes the
JSON the site plots. They are separate rather than one entry point because
their dependencies and runtimes differ wildly — one needs TensorFlow, another
makes rate-limited API calls.

**They import the projects rather than reimplementing them.** This is the point
of the layout. Every number the site shows — every interval, p-value and
backtest — comes from the same function the project's command line calls, so a
chart cannot quietly disagree with the package it is supposed to be showing.
The projects are not pip-installed here; each script puts the relevant
`inference/<name>/src` on `sys.path` via a small `use()` helper,
because CI checks the repo out and runs the generator rather than installing
seven packages.

| Script | Imports | Needs | Runtime |
|---|---|---|---|
| `generate_demo_data.py` | — (SWE/AI demos) | pandas, yfinance | ~2 min (62 tickers) |
| `generate_notebook_results.py` | `churn`, `news_signal`, `threat_structure`, `rec_eval` | scikit-learn, SciPy | ~3 min |
| `generate_weather_results.py` | `climate_trend` | requests | ~1 min (rate-limited, backs off) |
| `generate_stockbond_results.py` | `allocation` | yfinance, SciPy | ~30 s |
| `generate_bitcoin_results.py` | `btc_forecast` | TensorFlow, yfinance | ~3 min |
| `generate_piano_results.py` | `arranger` | — | ~20 s |

```bash
pip install pandas numpy scikit-learn scipy yfinance requests tensorflow
python site/scripts/generate_demo_data.py
python site/scripts/generate_notebook_results.py
python site/scripts/generate_weather_results.py
python site/scripts/generate_stockbond_results.py
python site/scripts/generate_bitcoin_results.py
python site/scripts/generate_piano_results.py
npm test          # the ports are checked against the regenerated fixtures
```

Every script that has a date range defaults its end to **today** and takes
`--start` / `--end` to override. Nothing is pinned to a hardcoded end date, so
a generator re-run months from now widens the window rather than reproducing an
old one. The analysis settings are arguments too, so the published charts are a
default rather than the only thing the code can produce:

```bash
python site/scripts/generate_stockbond_results.py \
    --start 2015-01-01 --tickers SPY,QQQ,TLT,GLD,SHV \
    --lookback 252 --rebalance-every 21 --cost-bps 5
python site/scripts/generate_weather_results.py \
    --cities London,Tokyo --projection-years 50 --bootstrap-draws 5000
python site/scripts/generate_bitcoin_results.py \
    --train-fraction 0.7 --test-size 90 --no-lstm
```

Only `generate_demo_data.py` runs on a schedule (weekly, see
`.github/workflows/refresh-data.yml`). The rest are run by hand — though the
market and weather ones fetch live, so re-running any of them does move the
window forward.

One exception, deliberately: the golden fixtures in `generate_demo_data.py` pin
a fixed ticker set and date window. They are the reference the TypeScript ports
are tested against, and a floating reference would mean the tests could never
fail.

## Things worth knowing

**The piano generator writes a fixture, not a chart.** The arranger runs in the
browser so a visitor can type any chords they like, which means the engine
exists twice. `piano-golden.json` records what the Python says across 120
combinations of progression, difficulty level and style, and
`src/demos/lib/arranger.test.ts` asserts the port agrees on every voicing, cost
and rule violation. Nothing in that file is used to draw anything. It also
stores costs to twelve decimals rather than the six that reads nicely, for the
same reason the weather fixture stores six: a rounded fixture forces a
tolerance loose enough to hide a real disagreement.

**Two of these analyses are also implemented in TypeScript.** The weather demo
lets a visitor look up any city, which is fetched and analysed in the browser —
so `src/demos/trend.ts` is a port of `climate_trend`, and `trend.test.ts` checks
it against the Python output for all six bundled cities. That test is why
`nb-weather.json` stores annual temperatures to six decimals rather than three:
at three, rounding the *input* moved the answers by ~1e-4, which would have
forced a tolerance loose enough to hide a genuine disagreement.

**NaN is not valid JSON, and some of these statistics are legitimately NaN.**
Mann-Kendall is a rank test with no standard error to report, and the naive
price forecast abstains on every day so its hit rate is undefined rather than
zero. Both are emitted as `null` and rendered as "—" or "no call", not as a
zero that would read as a real measurement.

**The bitcoin script reads the packaged daily bars, not the 127 MB archive.**
`btc_forecast` ships `btcusd_daily.csv` (230 KB, already resampled from the
minute file), and the script tops it up from Yahoo so the window reaches today.
Rebuilding the daily file from the raw minute trades is
`btc_forecast.data.build_daily_from_minutes`.

**The bitcoin lookback is 90 days, not 60.** That comes from the saved model's
own input shape; the project README says 60. The model is the authority.
