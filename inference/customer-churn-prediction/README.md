# Customer Churn Prediction

Telco churn, treated as what it actually is: **right-censored survival data
driving a spending decision**, not a binary classification score.

73.5% of these 7,043 customers had not left when the data was cut. Their
lifetime is not "no churn" — it is *at least* their current tenure, and the
difference is the whole problem. A classifier sees a one-month customer who
hasn't left and a six-year customer who hasn't left as the same row.

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
churn                      # the whole analysis
churn --section survival   # or one part of it
churn --offer-cost 50 --acceptance 0.2   # stress-test the economics
pytest -q                  # 105 tests
```

---

## What the data supports that the notebook didn't use

```
  S( 6 months) = 0.885   95% CI [0.877, 0.892]
  S(12 months) = 0.843   95% CI [0.834, 0.852]
  S(24 months) = 0.789   95% CI [0.778, 0.799]
  S(60 months) = 0.664   95% CI [0.650, 0.678]

  median lifetime: never reached inside the window
  expected months retained over 5 years: 46.8

  Month-to-month   n=3875  S(24) = 0.586
  One year         n=1473  S(24) = 0.978
  Two year         n=1695  S(24) = 1.000
```

**The median lifetime is undefined, and that is the correct answer.** More than
half of these customers are still subscribed at the end of the window, so the
median has not happened yet. Quoting a number would mean inventing the part of
the curve that hasn't occurred. The restricted mean — 46.8 of the next 60
months — is the summary that *is* answerable.

Kaplan-Meier, the log-rank test and Cox regression are implemented from
scratch in [`survival.py`](src/churn/survival.py). That's only defensible if
the arithmetic is checked, so every one is compared against statsmodels'
independent implementation in the tests: Kaplan-Meier agrees to 1e-16, the
log-rank statistic to 1e-9, Cox coefficients and standard errors to 1e-8.

## Cox regression, and the assumption nobody checks

| effect | hazard ratio | 95% CI |
|---|---:|---|
| each step up in contract length | **0.199** | [0.175, 0.226] |
| pays by electronic check | 1.797 | [1.562, 2.066] |
| has a partner | 0.596 | [0.535, 0.664] |
| has online security | 0.542 | [0.418, 0.704] |

Concordance index **0.870**, against the classifier's 0.845 AUC on the same
rows. The survival model ranks better because it can see *when* people left.

Then the caveat, reported rather than buried: **the proportional-hazards
assumption fails for 16 of the 20 covariates.** The model assumes a covariate's
effect is a constant multiplier — the same in month 2 as in month 60 — and
correlating the scaled Schoenfeld residuals against time says it isn't. Those
hazard ratios are averages over effects that move. A stratified or
time-varying model is the honest next step, and the number above has an
asterisk on it until then.

## Three bugs in the original notebook

**`y_prob` was never defined.** The evaluation loop called
`roc_curve(y_test_numeric, y_prob)` for a variable that is assigned nowhere in
the notebook. Running `ruff` over it reports `F821 Undefined name 'y_prob'`
twice, along with three undefined `np`.

**Eleven customers were told they had paid $2,283.** `TotalCharges` holds a
blank string for eleven rows; the notebook coerced them to NaN and filled with
the column mean. All eleven have `tenure == 0` — they signed up and haven't
been billed. The correct value is exactly 0, and it is derivable rather than
guessable.

**Six columns were exact duplicates of another column.** Every add-on service
has a "No internet service" level, and all six are the same 1,526 customers as
`InternetService == "No"`; `MultipleLines == "No phone service"` likewise
restates `PhoneService == "No"`. One-hot encoded as they stand, the design
matrix is 27 columns of rank 21 and the Cox Hessian is singular. The notebook
never hit this because label-encoding collapses each column to one number,
which hides the collinearity rather than removing it.

## What the shortcuts were actually worth

I expected the leakage to be the story. It wasn't — and reporting that is the
point of measuring instead of asserting.

```
one 80/20 split, scaler fitted on everything : AUC 0.8617   <- the notebook
one 80/20 split, scaler fitted on train only : AUC 0.8615
the leak was worth                           : +0.0002

5-fold out-of-fold, preprocessing inside the pipeline:
  logistic           AUC 0.8449  95% CI [0.8343, 0.8546]
  random_forest      AUC 0.8438  95% CI [0.8332, 0.8539]
  gradient_boosting  AUC 0.8288  95% CI [0.8182, 0.8386]
```

**The leak was worth 0.0002 of AUC. The lucky split was worth 0.017** — and
0.8617 sits outside the 95% interval the cross-validated estimate supports.
The methodological error everyone names cost nothing here; reporting one split
as though it were an estimate cost eighty times more. The three models also tie
within their intervals, so "random forest was best" was never a finding.

## The finding that matters: rebalancing destroys the probabilities

| | AUC | mean predicted | ECE | Brier skill |
|---|---:|---:|---:|---:|
| `class_weight="balanced"` | 0.8449 | 0.414 | 0.1490 | +0.149 |
| unweighted | 0.8450 | 0.266 | **0.0120** | **+0.305** |

Actual churn rate: 0.265.

Rebalancing changed the ranking by **0.0001 of AUC** and made the probabilities
roughly twice too large. SMOTE, which the notebook used, does the same thing —
that is what rebalancing *is for*. Customers the balanced model scores at 0.45
churn 22% of the time; at 0.65, 37%.

AUC never notices, because it only asks whether churners outrank non-churners
and is unchanged if you square every probability. It stops being harmless the
moment the score is multiplied by a dollar amount — which is exactly what
happens next.

## Turning a probability into a decision

A churn model doesn't retain anybody. Someone has to be offered something, the
offer costs money, and most people who accept were never going to leave.

```
assumptions: $30 per offer, 30% accept, 30% margin, 24-month horizon
value at stake: median $378, max $854 (from each customer's own survival curve)

best threshold 0.25: call 3,022, net $83,498
default 0.50       : call 1,570, net $67,860   ($15,638 left on the table)
```

**0.5 has no claim on being the right cut-off.** It is only optimal when the
two errors cost the same, and here contacting a happy customer costs one
discount while losing an unhappy one costs their whole remaining value.

An honest note on the calibration finding: if you tune the threshold by search
on the same data, the mis-calibrated model lands in almost the same place
(0.49, $83,857) — the threshold absorbs the bias. What you lose is the ability
to *derive* the cut-off from the economics rather than grid-search it, to read
a score as a probability, and to move that threshold to next quarter's data.

### Where the survival model pays for itself

```
same budget of 1,000 calls:
  by_probability       $46,317
  by_expected_value    $61,496     <- +33% for the same spend
  random               $ 1,172
  everyone             $ 5,602
```

Ranking by churn probability spends the budget on whoever is most likely to
leave, regardless of whether they were worth keeping. Ranking by probability ×
value needs to know how long each customer *would* have stayed — which is the
area under their own survival curve, and is not something a classifier can
produce. "Will churn" is the same label for a customer with eight months left
and one with four years.

The optimiser can also return "run no campaign", because when the offer costs
more than the customer is worth that is the right answer and it has to be on
the menu.

## Layout

```
src/churn/
  data.py         load, repair, validate; the design matrix     (pure)
  survival.py     Kaplan-Meier, log-rank, Cox, concordance      (pure)
  classify.py     pipelines, cross-validation, bootstrap CIs
  calibration.py  reliability, Brier, ECE                       (pure)
  economics.py    expected value, thresholds, targeting         (pure)
  cli.py          the report
tests/            105 tests, statsmodels used only to check the maths
notebooks/        the original, kept as the record of what this replaced (marked superseded)
```

## The assumption fails. Stratifying does not fix it.

The model rests on one claim: a covariate's effect is a constant multiplier on
the hazard, the same in month 2 as in month 60. The Schoenfeld test says
otherwise for **16 of 20 covariates**, and the README used to stop there,
noting that "a stratified model would be the next step".

It is the textbook next step, so it is now implemented — and it does not work:

```
                            covars  violations  mean |corr|     log-lik
Cox                             20          16        0.112    -13884.6
stratified on Contract          19          16        0.114    -13329.7
```

Stratifying moves `Contract` out of the linear predictor and gives each of its
three levels its own baseline hazard, free to take any shape. The fit improves
a great deal — 555 log-likelihood points, which it must, since the model is
strictly more flexible. **The violation is untouched.** Still 16, and the mean
absolute residual correlation is fractionally *worse*.

Two things are worth saying about that number before trusting either column.
With 1,869 events, a correlation of 0.045 already clears p < 0.05, so counting
violations at that threshold mostly measures the sample size. The magnitudes
are what matter, and at 0.11 to 0.27 they are far above that floor — the
violation is real, not an artefact of power.

### Why it does not work, and what is actually happening

Stratifying on `Contract` only absorbs *`Contract`'s* non-proportionality. The
problem is broader than one variable, and `compare_periods` shows it by
fitting the same covariates before and after the first year:

```
period split at 12 months        early    late
Contract                          0.06 ->  0.25   x4.5
InternetService (fiber)           1.15 ->  3.04   x2.6
PhoneService                      0.87 ->  1.83   x2.1   reverses
StreamingTV                       0.77 ->  1.44   x1.9   reverses
StreamingMovies                   0.71 ->  1.31   x1.8   reverses
```

These effects do not merely weaken. **Six of them change sign.** Streaming is
protective in the first year and a risk factor afterwards; a long contract
nearly eliminates early churn and matters four and a half times less later.

That is a statement about the business, not a modelling nuisance. Early churn
and late churn are different phenomena — early, a contract locks you in and
extra services are a sign of engagement; later, the same services mark a
customer paying for more than they use. A single hazard ratio averages those
two regimes and describes neither.

So the honest reporting is: the coefficients in the summary above are
time-averages over an effect that reverses, the stratified model does not
repair that, and the period split is what should be read instead. Fixing it
properly needs time-varying coefficients — episode splitting with the
covariates interacted against a function of time — which is a change to the
likelihood rather than a change to the design matrix, and is not done here.

## Limits

- **Proportional hazards fails**, as above, and stratifying does not fix it —
  measured, not assumed. The hazard ratios are time-averages over effects that
  reverse within the first year. The remedy is time-varying coefficients via
  episode splitting, which changes the likelihood rather than the design
  matrix and is not implemented.
- **`compare_periods` splits at one cut-off**, chosen at 12 months because it
  is interpretable, not because anything identified it as a breakpoint. A
  changepoint search would be the honest way to pick it.
- **The economics are assumptions, not findings.** Offer cost, acceptance rate
  and margin are arguments to `Campaign` precisely so the conclusion can be
  stress-tested; none of them can be read off this dataset.
- **There is no experiment here, so no uplift model.** Targeting by expected
  value is still a proxy: the right target is who would *change their mind
  because of the offer*, and answering that needs a randomised holdout the
  data doesn't contain.
- **One snapshot, no time dimension across customers.** Everything is measured
  at a single cutoff, so nothing here detects drift.

## Dataset

[Telco Customer Churn](https://www.kaggle.com/datasets/blastchar/telco-customer-churn) —
7,043 customers, 21 columns, bundled in [`data/`](data/).
