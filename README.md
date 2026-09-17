# Anita Huang — Projects

**[View the project site →](https://anita-huangz.github.io/)**

[![The portfolio site](site/docs/screenshot.png)](https://anita-huangz.github.io/)

AI platform engineering, backend systems, and quantitative work. Everything
here lives in one repository, and every project marked ✅ runs its full test
suite offline in [CI](.github/workflows/ci.yml) — no network, no API keys —
across Python 3.11, 3.12, and 3.13.

**430 tests.** I've noted what each project gets wrong as well as what it does,
because the bugs are usually the more interesting half.

---

## AI Platform

### ✅ [SEC Filing Intelligence](ai-platform-projects/sec-filing-intelligence) · 167 tests

Ask a question about a public company and get an answer with every claim cited
to a specific SEC filing — then independently verified against the evidence that
produced it. Served as **both an HTTP API and an MCP server**.

**In** — a ticker and a plain-English question: `AAPL`, *"What supply chain
risks does Apple disclose?"*
**Out** — a cited answer plus structured findings, each carrying an accession
number and filing date, a verified/unverified verdict, and the run's token
count, dollar cost, and latency.

The agent writes a research plan, then calls up to four tools against SEC
EDGAR — listing filings, pulling a named section out of a 10-K, fetching
reported XBRL figures, measuring the price move after a filing date. A separate
verifier pass re-reads the gathered evidence and checks each citation actually
supports its claim before the answer is returned.

```
plan ─▶ research ⇄ tools ─▶ analyze ─▶ verify
```

- **Multi-provider model access** — Anthropic, AWS Bedrock, and a deterministic
  replay provider behind one interface. Nothing above the provider layer imports
  a vendor SDK, which is what lets CI exercise the whole agent graph with no key
  and no spend.
- **Citations are audited, not trusted** — a verifier node checks each finding
  against gathered evidence and can mark the answer unverified.
- **Bounded execution** — a hard tool-call ceiling plus least-privilege
  capability grants. Tools outside a grant are hidden from the model *and*
  refused if it asks anyway.
- **Telemetry** — tokens, estimated USD, latency percentiles, and failure kinds,
  sliced by model and tool. Cached reads bill at 0.1× the *input* rate, which is
  the usual way cost tables overstate spend.
- **Evaluation harness** — accuracy, consistency, reliability, latency, and cost
  measured separately, because they fail independently.
- **A React UI** that streams the agent's run over server-sent events as it
  happens.

`make demo` runs the whole stack against real SEC EDGAR with **no API key**.

**Python · FastAPI · MCP · Pydantic · LangGraph · Claude · AWS Bedrock · Redis ·
Docker · React · TypeScript**

---

## Software Engineering

Ordered by engineering complexity — interacting subsystems, algorithmic depth,
and how much the correctness depends on domain reasoning. Not line count: the
last entry is the smallest project here and also the subtlest.

### ✅ [Factor Portfolio Simulator](software-engineer-projects/factor-based-portfolio-simulator) · 52 tests

Point-in-time backtest of cross-sectional equity factor strategies, with
Fama-French 3-factor attribution.

Fixed a **look-ahead bias that overstated total return by 92 percentage
points** — factors were computed once from the entire sample and reused at every
rebalance, so the 2021 allocation was picked using 2024 returns.
[`examples/lookahead_demo.py`](software-engineer-projects/factor-based-portfolio-simulator/examples/lookahead_demo.py)
reproduces both loops over identical prices:

| | point-in-time | full-sample (bug) |
|---|---:|---:|
| total return | 2.85% | **95.43%** |
| Sharpe | 0.14 | **1.42** |

Also: performance metrics were computed on the last five rows of the backtest
while describing three years.

**Python · pandas · NumPy · statsmodels · yfinance**

### ✅ [Trie Search](software-engineer-projects/web-crawler-and-search-engine) · 58 tests

Crawls a website, indexes every word into a trie, searches by prefix or
single-character wildcard.

`Trie.__iter__` yielded `(key, value)` tuples — and since `MutableMapping`
builds `keys()`, `values()`, and `items()` on top of `__iter__`, all three
raised and `dict(trie)` didn't work. The class claimed a contract it failed.

**Python · httpx · lxml · data structures**

### ✅ [Course Catalog & Scheduling](software-engineer-projects/course-catalog-scheduling-system) · 52 tests

Searches a course catalog and builds a schedule that doesn't double-book you.
A meeting is a day plus a **half-open** interval, which is the whole conflict
rule: a class ending at 7:30 and one starting at 7:30 are back to back, not a
conflict.

Prefix search was actually *substring* search, so `"530"` matched
`MPCS 53014-1` via digits in the middle of the number.

**Python · csv · interval logic**

### ✅ [Card Game](software-engineer-projects/card-game-system) · 48 tests

A single-player poker-style draw game. Two scoring bugs, both from testing for
an *exact* count in a seven-card hand: six- and seven-card flushes scored as
nothing, and two triples scored as three-of-a-kind rather than a full house.

**Python · rich · OOP**

### ✅ [Earnings Drift Tracker](software-engineer-projects/earnings-drift-tracker) · 29 tests

Measures post-earnings-announcement drift against the size of the analyst
surprise. Announcements landing on a non-trading day now fall back to the prior
session's close; requiring an exact index match silently dropped a large and
non-random slice of events.

**Python · pandas · NumPy · REST APIs**

---

### ✅ [fastcache — an O(1) LRU cache](software-engineer-projects/performance-optimization) · 24 tests

An LRU cache decorator benchmarked against `functools` and against the
list-based approach it replaced. The original called `list.remove` on every
cache hit — a linear scan on the one path a cache exists to make fast.

Across cache sizes 128 → 32,768 the list-based hit path slows **8.5×** while
this one stays flat at ~0.45µs.

**Python · threading · benchmarking**

## Data Science

Exploratory analyses rather than engineered packages — no test suites. Ordered
by complexity, most involved first: depth of method, how much domain reasoning
the result rests on, and how easy it is to get quietly wrong.

### 1. [Stock-Bond Portfolio Optimisation](data-science-projects/stock-bond-portfolio-analysis)
Allocates across five ETFs by solving a constrained optimisation whose objective
trades factor-risk exposure against Sharpe, with weights informed by a
regression and conditioned on the volatility regime. Not textbook
mean-variance — the Sharpe preference is swept across twelve values so you can
watch the allocation move from risk-matching to return-seeking.
**463 lines, SPY/IWM/TLT/LQD/SHV, 2012–2024** · SciPy, statsmodels, yfinance

### 2. [Bitcoin Price Forecasting](data-science-projects/bitcoin-and-asset-trading)
A stacked LSTM with dropout, trained on rolling 60-day windows cut from 127 MB
of minute-resolution trades resampled to daily bars. The hard part of a
sequence pipeline isn't the architecture — scale before the split and the test
set leaks into training.
**TensorFlow, Keras, scikit-learn**

### 3. [Fake News Detection](data-science-projects/fake-news-detection)
TF-IDF over article text, sentiment polarity, and structural metadata, compared
across several classifiers under cross-validation. **The reportable result is
negative:** metadata alone scores an ROC AUC of 0.46 — at or below a coin
flip — so none of those structural signals separate a fake article here.
**4,000 articles, 50.6% fake** · scikit-learn, XGBoost, TextBlob

### 4. [E-commerce Recommendations](data-science-projects/personalized-recommendations-for-e-commerce)
Joins customer behaviour against a product catalogue across boosting,
ensembles, text features and seasonality. The data undercuts the premise: the
three customer segments barely differ in average order value, so the segment
label carries little signal.
**10,000 customers × 10,000 products** · scikit-learn, XGBoost

### 5. [Cybersecurity Threat Analysis](data-science-projects/global-security-threats)
Six unsupervised methods over a decade of incidents — PCA and t-SNE, K-Means
and DBSCAN, Isolation Forest and Local Outlier Factor. Unsupervised work is
harder to judge than it looks: with no ground truth, a clean separation can be
an artifact of handing the clusterer the same columns the projection used.
**3,000 incidents, 2015–2024, 150 flagged anomalous** · scikit-learn

### 6. [Customer Churn Prediction](data-science-projects/customer-churn-prediction)
A supervised pipeline reaching AUC 0.83 — and a demonstration of why accuracy
is the wrong headline. Recall is 49.7%, so it catches half the customers who
actually left, and 78.9% accuracy is near what you'd score predicting nobody
churns. The strongest pattern needs no model: **month-to-month churns at 42.7%
against 2.9% on a two-year contract.**
**7,032 customers, 26.6% churned** · scikit-learn, seaborn

### 7. [Weather Trends & Forecast](data-science-projects/weather-trends-and-forecast)
Pulls hourly ERA5 reanalysis from the Open-Meteo API, extracts long-run
temperature trends, and projects them forward. One caveat stated plainly: the
legislation-influence feature is synthetic, so it demonstrates the mechanism
rather than measuring a real effect.
**3 scripts, ~200 lines** · pandas, scikit-learn, requests

## Repository layout

```
ai-platform-projects/     the AI platform
software-engineer-projects/   six engineered Python packages
data-science-projects/    exploratory notebooks
site/                     the portfolio site (React + Vite)
.github/workflows/        CI and GitHub Pages deployment
```

Each engineered project is self-contained: its own `pyproject.toml`, its own
test suite, its own README explaining the design decisions and what was wrong
before.

## Running anything locally

Every Python project follows the same shape:

```bash
cd <project>
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
pytest -q
ruff check .
```

The portfolio site:

```bash
cd site && npm install && npm run dev
```

## Conventions

- **Pure logic is separated from I/O.** Computation modules don't print, fetch,
  or plot — which is what makes the arithmetic directly testable.
- **Tests run offline.** Network calls are faked at the transport layer
  (`httpx.MockTransport`) and model calls through a replay provider. No test
  needs a key or a connection.
- **Failures are typed and reported, not swallowed.** A bare
  `except: continue` makes a broken run look like an empty one.
- **READMEs state the limits.** Every project has a "notes" or "limits" section
  covering what it doesn't do and where the numbers shouldn't be trusted.
