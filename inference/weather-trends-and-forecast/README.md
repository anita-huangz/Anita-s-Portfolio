# Weather Trends & Forecast

Warming rates for six cities over 75 years — and the part the original scripts
got wrong, which is not the slope but **the error bar around it**.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
climate-trend                            # the whole analysis
climate-trend --city Tokyo               # a different city
climate-trend --section autocorrelation  # or one part
pytest -q                                # 24 tests
```

---

## Every city is warming

| city | Sen slope °C/decade | 95% interval | year-to-year sd | decades to notice |
|---|---:|---|---:|---:|
| London | +0.244 | [+0.184, +0.305] | 0.69 | 2.8 |
| New York | +0.227 | [+0.150, +0.305] | 0.79 | 3.5 |
| Tokyo | +0.201 | [+0.148, +0.255] | 0.56 | 2.8 |
| Reykjavik | +0.189 | [+0.111, +0.265] | 0.74 | 3.9 |
| Nairobi | +0.126 | [+0.092, +0.157] | 0.37 | 2.9 |
| Sydney | +0.111 | [+0.072, +0.144] | 0.40 | 3.6 |

Every interval excludes zero. The last column is why nobody notices from
memory: **a decade of warming is smaller than one year's natural variation**
in all six cities, so any two adjacent years tell you nothing.

## The error bar was wrong, and by how much

Ordinary least squares assumes the residuals are independent. Temperature does
not work that way — a warm year follows a warm year, because oceans and soil
carry heat across the calendar boundary. Positive autocorrelation means there
are fewer effectively independent observations than rows, so the OLS standard
error is too small and its interval too narrow.

| city | lag-1 | p | Durbin-Watson | effective n | OLS SE understated by |
|---|---:|---:|---:|---:|---:|
| Tokyo | +0.403 | 0.0002 | 1.12 | 32/75 | **53%** |
| Reykjavik | +0.367 | 0.0007 | 1.25 | 35/75 | 47% |
| Sydney | +0.253 | 0.0142 | 1.48 | 45/75 | 30% |
| New York | +0.232 | 0.0223 | 1.51 | 47/75 | 27% |
| Nairobi | +0.211 | 0.0336 | 1.55 | 49/75 | 24% |
| London | +0.200 | 0.0414 | 1.58 | 50/75 | 23% |

**Significant in all six.** Tokyo's 75 years are worth about 32 independent
ones, so its naive interval is half the width it should be.

### Four methods, one slope, four different widths

```
London, 75 annual means, 1950-2024

method                   slope   std err   95% interval                   p
OLS                    +0.2346    0.0294   [+0.1760, +0.2933]  1.57e-11
Newey-West (lag 3)     +0.2346    0.0352   [+0.1644, +0.3049]  4.43e-09
block bootstrap (4y)   +0.2346    0.0323   [+0.1712, +0.2978]  0.00e+00
Mann-Kendall / Sen     +0.2438       nan   [+0.1836, +0.3050]  2.31e-09
```

They share no assumptions and land in the same place, which is the point:

- **Newey-West** corrects the OLS standard error for autocorrelation up to a
  chosen lag.
- **The moving-block bootstrap** resamples contiguous blocks of *residuals*,
  reproducing the persistence without modelling it.
- **Mann-Kendall with Sen's slope** is rank-based and assumes nothing about the
  distribution — Sen's slope is the median of all pairwise slopes, so one freak
  year barely moves it where it would tug a least-squares line.

Only OLS disagrees, and only about the width.

## Two bugs I found by looking at the output

**The bootstrap was resampling the wrong thing.** The first version resampled
the *temperatures* against a fixed time axis, which scrambles the trend out of
the series: the interval came back as [−0.11, +0.11] around a point estimate of
+0.235, and p = 0.97. That is a null distribution, not a sampling distribution.
Residuals are what gets resampled, added back to the fitted line.

**A fixed Durbin-Watson cut-off of 1.5 was the wrong test.** DW's critical
values depend on the sample size and the number of regressors, and London's
1.576 sits *below* the 5% bound for 75 observations while being above the rule
of thumb — so it was reported as uncorrelated when it is not. The lag-1
correlation is now tested directly against its own standard error.

## What changed from the original scripts

- **90 days became 75 years.** A straight line fitted through three months of
  daily maxima measures the seasons, not a trend.
- **The synthetic "legislative influence" regressor is gone.** It was
  `generate_dummy_legislation_influence` — made-up numbers fed to a regression
  as a real feature, which can only inflate fit.
- **Daily maxima became annual means.** Part-years are dropped: a mean from 200
  days is not comparable to one from 365, and including it puts a spurious
  kink at each end of the record.

## Layout

```
src/climate_trend/
  data.py   annual means, centred decades, the year-to-year yardstick  (pure)
  trend.py  OLS, Newey-West, block bootstrap, Mann-Kendall/Sen,
            autocorrelation diagnostics                                (pure)
  cli.py    the report
  data/     14 KB of annual means, reduced once from ERA5 daily
tests/      24 tests; OLS and Newey-West checked against statsmodels
notebooks/  the original scripts, kept as the record
```

## Limits

- **Six cities is not the globe.** These are point locations from a reanalysis
  grid, chosen for spread, not a global average. Nothing here is an estimate of
  global warming.
- **A linear trend is a summary, not a model.** Warming has accelerated; a
  single slope over 75 years averages that away. A breakpoint or segmented fit
  would say more, and is the obvious next step.
- **No forecast.** The original projected a line forward 30 days. Extending a
  75-year trend to predict next month is not what the trend estimates, and the
  honest projection — line extended, uncertainty widening — is dominated by the
  year-to-year variation in the table above.
- **ERA5 is a reanalysis**, a physics model blended with observations, not raw
  measurement. It is the best available record for places and times nobody was
  measuring, and it is still a model.

## Data

[Open-Meteo ERA5 archive](https://open-meteo.com/en/docs/historical-weather-api)
— daily means 1950–2024, reduced to annual means and committed. Open-Meteo
allows browser requests, which is why the site's demo can look up any city
live without a proxy.
