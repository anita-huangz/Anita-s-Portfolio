# Stock-Bond Portfolio Optimisation

Mean-variance allocation across five ETFs, evaluated **out of sample** and
against the benchmark that keeps winning: **1/N**.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
allocation                          # the whole comparison
allocation --section out            # or one part
allocation --rebalance-every 21     # settings change the answer; they're arguments
pytest -q                           # 25 tests
```

4,201 trading days, 2010–2026, adjusted closes committed as 216 KB.

---

## Out of sample, with costs

| strategy | ann return | vol | Sharpe | max DD | turnover | cost drag |
|---|---:|---:|---:|---:|---:|---:|
| **equal weight (1/N)** | **+6.50%** | 8.02% | 0.83 | 22.6% | 1.8% | 0.00% |
| risk parity | +4.98% | 4.39% | 1.13 | 13.9% | 5.7% | 0.01% |
| maximum Sharpe | +1.80% | 6.09% | **0.32** | 20.0% | 14.9% | 0.03% |
| minimum variance | +1.61% | 0.25% | 6.37 | 0.4% | 1.5% | 0.00% |

**1/N earns the most, and it is the only rule that estimates nothing.** This
reproduces DeMiguel, Garlappi and Uppal (2009), who tested fourteen
mean-variance strategies across seven datasets and found none reliably beat
naive diversification out of sample.

**Maximum Sharpe comes last on the Sharpe ratio it optimises** — 0.32 against
1/N's 0.83. It is the only rule here that needs expected returns, and expected
returns cannot be estimated well enough to optimise against: the standard error
on a mean return is roughly the volatility over the square root of the years,
which for equities is several percentage points on a number that is itself
several percentage points.

Minimum variance's Sharpe of 6.37 is an **artefact**, not a triumph: it holds
SHV — a short-Treasury fund — at 100%, so there is almost no volatility to
divide by. On a universe containing a cash-like asset, "minimise variance" has
an obvious and useless answer. Read its +1.61% return instead.

## In sample, which is what the original reported

| strategy | ann return | vol | Sharpe |
|---|---:|---:|---:|
| equal weight (1/N) | +7.13% | 8.21% | 0.88 |
| maximum Sharpe | +1.45% | 0.26% | **5.61** |
| risk parity | +5.38% | 6.10% | 0.89 |

The notebook estimated factor loadings and expected returns on a training
period, optimised, and reported the resulting portfolio's statistics — which
describe a portfolio chosen *with knowledge of* the returns it is then scored
on.

**Maximum Sharpe reports 5.61 in sample and 0.32 out of it, a 17× collapse.**
1/N moves from 0.88 to 0.83, because it has no parameters to overfit. That gap
is the whole argument, and the notebook had no way to see it.

## Why: estimation error reaching the portfolio

| strategy | weight instability | turnover per rebalance |
|---|---:|---:|
| equal weight (1/N) | 0.0000 | 1.8% |
| minimum variance | 0.0007 | 1.5% |
| risk parity | 0.0205 | 5.7% |
| maximum Sharpe | **0.0567** | **14.9%** |

Maximum Sharpe rewrites 15% of the book every quarter. The underlying assets
did not change that much — what changed is the sample mean it is chasing. That
instability *is* the estimation error, made visible.

Both defences against it are implemented: **Ledoit-Wolf shrinkage** toward a
constant-correlation target, with the intensity reported rather than hidden,
and the observation that **minimum-variance and risk-parity portfolios ignore
expected returns entirely** — which is why they hold up better.

## Two bugs found by writing tests

**Turnover was measured against the wrong thing.** `average_turnover` compared
consecutive *target* weights, so it reported 1/N as having zero turnover. But
between rebalances the book drifts with prices, and returning to a fixed target
still requires trading — 1.8% per quarter here. Turnover is now recorded as
actually traded, and every strategy's cost drag was understated before.

**Two covariance conventions were mixed.** The shrinkage estimator divided by
`n` (the classical Ledoit-Wolf derivation) while `sample_covariance` divided by
`n − 1` (pandas' default), so the shrunk matrix's diagonal disagreed with the
sample variance by a factor of `n/(n−1)`. Small, silent, and wrong.

## What went, from the original notebook

- **`adjust_factor_weights_based_on_regression`**, which multiplied a factor
  loading by 1.5 if it exceeded 0.5, by 1.2 if it exceeded 0.2, and by 1.0
  otherwise. Three magic constants and three thresholds, none justified.
- **`normalize_client_weights`**, which iterated over factor names and indexed
  the result as if they were asset names.
- **The in-sample report**, replaced by the rolling backtest above.

## Layout

```
src/allocation/
  data.py      adjusted closes, returns, annualised summaries      (pure)
  estimate.py  sample covariance, Ledoit-Wolf shrinkage            (pure)
  optimise.py  1/N, min-variance, max-Sharpe, risk parity          (pure)
  backtest.py  rolling out-of-sample with costs; in-sample foil    (pure)
  cli.py       the report
  data/        216 KB of adjusted closes for five ETFs
tests/         25 tests; shrinkage cross-checked against scikit-learn
notebooks/     the original, kept as the record (marked superseded)
```

## Limits

- **Five assets is a small universe**, and 1/N's advantage grows with the
  number of assets, so this understates the effect rather than overstating it.
- **Long-only, no leverage.** Allowing shorts makes every optimised portfolio
  more extreme and the out-of-sample collapse worse, so this is the
  conservative setting.
- **One 16-year sample, one asset class mix.** The conclusion holds at 21-day
  and 126-day rebalancing — there is a test — but this is not a general proof.
- **No factor model.** The original regressed returns on Fama-French factors to
  build expected returns. That is a more sophisticated way to estimate a number
  that still cannot be estimated well enough, and the backtest here shows what
  relying on it costs.
- **Costs are a flat bps charge on turnover.** Real execution has spread and
  market impact, both worse for the high-turnover strategies.

## Data

Adjusted daily closes for SPY, IWM, TLT, LQD and SHV from Yahoo Finance,
2010–2026, bundled in [`src/allocation/data/`](src/allocation/data/). Adjusted,
because dividends are most of the return on the bond funds and SHV looks flat
without them.
