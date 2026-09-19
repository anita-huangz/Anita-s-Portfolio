# Bitcoin Price Forecasting

An LSTM against a one-line baseline, evaluated properly. The finding is
negative and it is the point: **no forecast here carries usable information
about price changes, and the ones that look like they might are destroyed by
transaction costs.**

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
btc-forecast                       # the whole evaluation
btc-forecast --section trading     # or one part
btc-forecast --section lstm        # needs tensorflow
pytest -q                          # 64 tests
```

4,825 daily bars, 2012-01-01 to 2025-03-17, reduced once from the 127 MB
minute file and committed as a 230 KB CSV.

---

## The LSTM against "tomorrow equals today"

| forecast | RMSE | R²(returns) | directional |
|---|---:|---:|---|
| LSTM (honest scaling) | 22,283 | **−206.4** | 49.0% [46%, 52%] |
| LSTM (as the notebook wrote it) | 13,867 | −58.5 | 49.7% [47%, 53%] |
| naive — tomorrow equals today | **1,401** | 0.0 | makes no call |

**Diebold-Mariano: DM = +18.03, p = 7.9e-63. The better forecast is the naive
one.** That is the upgrade over "16× worse": a ratio has no standard error on
it, and forecast errors on consecutive days are correlated, so the comparison
needs a test with a HAC correction rather than a division.

Three things that table is doing that the notebook's could not:

**R² on returns, not RMSE on levels.** Predicting "no change" every day scores
exactly 0. The LSTM scores **−206**, meaning its implied return forecast is two
hundred times worse than saying nothing. A model can track a price level
convincingly — and the chart does — while carrying no information about the
changes, and only the change is tradeable.

**An interval on the directional accuracy.** 49.0% with a 95% interval of
[46%, 52%] is a coin flip. The point estimate alone invites a conclusion the
sample cannot support.

**The naive forecast abstains rather than failing.** It predicts no change, so
it makes no directional call. Scoring that as 0% correct would report the
random walk at zero accuracy, which looks like a finding and is an artefact.

## The scaler leak

The notebook's sequence was:

```python
scaler = MinMaxScaler()
scaled = scaler.fit_transform(daily_close)   # the WHOLE series
X, y = create_sequences(scaled, 90)
X_train, X_test = X[:split], X[split:]       # split AFTER scaling
```

`MinMaxScaler` divides by `max - min`. Bitcoin's maximum is in the *test*
period, so the training data was normalised using the all-time high before it
happened — the model is told, in the units it learns in, how high the price
will eventually go.

```
training data ends 2022-07-27, highest price seen  $67,774
highest price in the whole series                 $106,187
range the leaky scaler used is                       1.57x wider
share of that scale never reached in training        36.2%
```

It makes the model look **1.61× better** than it is (RMSE 13,867 against
22,283) — which lines up with the 1.57× range inflation almost exactly.

## Walk-forward, instead of one lucky split

The notebook took the last 20% as a test set. On a time series that is one
experiment, and bitcoin's last 20% contains the run to $100k, so the score
describes that regime rather than the method. 21 rolling origins, expanding
window, non-overlapping test blocks:

| forecast | mean RMSE | fold range | mean R²(returns) | folds with R² > 0 |
|---|---:|---|---:|---:|
| naive | 680 | $5 – $2,076 | 0.0000 | 0/21 |
| drift | 681 | $5 – $2,066 | −0.0012 | 11/21 |
| ewma_10 | 1,183 | $9 – $3,594 | −2.1256 | 0/21 |
| ar5_returns | 687 | $6 – $2,083 | −0.0276 | 3/21 |

**The same method scores $5 in one fold and $2,076 in another.** That spread is
the argument against ever quoting a level-RMSE: it is a statement about the
price level, not about the forecast. And no baseline carries return information
on average — drift is above zero in 11 of 21 folds, which is what a coin does.

Every forecast is refitted at every origin, including the autoregression. That
is the expensive part and the whole point.

## Does it make money?

Long when the forecast says up, cash otherwise. Long/flat rather than
long/short, because shorting bitcoin has borrow costs and liquidation risk a
daily-bar backtest cannot model honestly.

| signal | 0 bps | 10 bps | 30 bps | trades | in market |
|---|---:|---:|---:|---:|---:|
| ewma_10 | +115.2% | +85.0% | +36.8% | 151 | 43% |
| ar5_returns | +158.5% | +93.3% | **+8.0%** | 291 | 76% |
| drift | +397.9% | +397.4% | +396.4% | 1 | 100% |
| **buy & hold** | **+397.9%** | | | 1 | 100% |

Buy and hold: Sharpe +1.71, max drawdown 27.2%. **Nothing beats it.**

Two things worth naming. AR(5) turns +158% into +8% once you pay 30 bps to
trade 291 times — 51% directional accuracy is not an edge, it is a toll. And
the drift forecast is long on **100%** of days, so it is buy-and-hold wearing a
model's clothes; its 53% directional accuracy is not timing anything, it is
noticing that bitcoin went up.

## Bugs found while building this

**`total_return` discarded the first day.** `(1 + r).cumprod()` already
measures growth from 1, so its first entry is `1 + r₀`; dividing by it throws
that day away. On a two-day window that is half the result. A test on a
three-row series caught it.

**The backtest dropped a day more than it needed to.** `previous` was taken
from the frame *after* rows without a forecast were removed, so the first
forecastable day went out with them.

## Layout

```
src/btc_forecast/
  data.py         daily bars, log returns, schema checks       (pure)
  baselines.py    naive, drift, EWMA, refitted AR(p)           (pure)
  metrics.py      RMSE/MAE/MAPE, Wilson intervals, return R2,
                  Diebold-Mariano with a HAC correction        (pure)
  walkforward.py  rolling-origin folds and evaluation          (pure)
  backtest.py     cost-aware long/flat, buy-and-hold           (pure)
  leakage.py      quantifies the MinMaxScaler leak             (pure)
  lstm.py         loads the saved model; tensorflow optional
  cli.py          the report
tests/            64 tests, none needing tensorflow
notebooks/        the original, kept as the record (marked superseded)
```

## Limits

- **The LSTM is not walk-forward evaluated.** Retraining at 21 origins is
  hours of compute for a result the baselines already settle, and scoring it
  on one split while the baselines face all of them flatters the LSTM.
- **Daily bars only.** Any edge at minute resolution is invisible here, and
  the raw file has it — this is a deliberate scope choice, not a claim that
  none exists.
- **No shorting, no leverage, no slippage model.** Costs are a flat bps charge
  on position changes; real execution is worse.
- **One asset.** Nothing here generalises to equities, which are far less
  volatile and far more mean-reverting.

## Data

[Bitcoin Historical Data](https://www.kaggle.com/datasets/mczielinski/bitcoin-historical-data)
— minute trades since 2012. `btc_forecast.data.build_daily_from_minutes`
regenerates the committed daily bars from it, so the CSV is reproducible
rather than a mystery artefact.
