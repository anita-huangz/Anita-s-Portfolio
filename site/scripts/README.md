# Demo data generators

Each script re-runs a project against its real source and writes JSON the site
plots. They are separate rather than one entry point because their
dependencies and runtimes differ wildly — one needs TensorFlow and reads
127 MB, another makes rate-limited API calls.

| Script | Needs | Runtime |
|---|---|---|
| `generate_demo_data.py` | pandas, yfinance | ~2 min (62 tickers) |
| `generate_notebook_results.py` | scikit-learn | seconds |
| `generate_weather_results.py` | requests | ~1 min (rate-limited, backs off) |
| `generate_stockbond_results.py` | yfinance, SciPy | ~20 s |
| `generate_bitcoin_results.py` | TensorFlow, zstandard | ~2 min, reads 127 MB |

```bash
pip install pandas numpy scikit-learn scipy yfinance requests zstandard tensorflow
python site/scripts/generate_demo_data.py
python site/scripts/generate_notebook_results.py
python site/scripts/generate_weather_results.py
python site/scripts/generate_stockbond_results.py
python site/scripts/generate_bitcoin_results.py
npm test          # the ports are checked against the regenerated fixtures
```

Every script that has a date range now defaults its end to **today**, and
takes `--start` / `--end` to override. Nothing is pinned to a hardcoded end
date, so a generator re-run months from now widens the window rather than
reproducing an old one.

```bash
python site/scripts/generate_stockbond_results.py --start 2015-01-01 --tickers SPY,QQQ,TLT,GLD,SHV
python site/scripts/generate_weather_results.py --cities London,Tokyo --projection-years 50
python site/scripts/generate_bitcoin_results.py --test-fraction 0.3
```

Only `generate_demo_data.py` runs on a schedule (weekly, see
`.github/workflows/refresh-data.yml`). The rest are run by hand because their
inputs are static datasets — though `generate_bitcoin_results.py` tops its
archive up from Yahoo, so re-running it does move the window forward.

One exception, deliberately: the golden fixtures in `generate_demo_data.py`
pin a fixed ticker set and date window. They are the reference the TypeScript
ports are tested against, and a floating reference would mean the tests could
never fail.

## Two things worth knowing

**The bitcoin script refits the scaler.** The project saved the model but not
the `MinMaxScaler`, so the transform has to be rebuilt. The script does it both
ways on purpose — fit on the training portion only, which is correct, and fit
on the whole series, which is the classic leak — because the gap between them
is the point.

**The bitcoin lookback is 90 days, not 60.** That comes from the saved model's
own input shape; the project README says 60. The model is the authority.
