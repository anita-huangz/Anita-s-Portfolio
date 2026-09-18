import type { Project } from "./types";

/**
 * Every project in the repository. Terminal output in `output` is real -- it
 * was captured by running the project, not written by hand.
 */
export const PROJECTS: Project[] = [
  {
    "slug": "sec-filing-intelligence",
    "title": "SEC Filing Intelligence",
    "category": "ai-platform",
    "featured": true,
    "summary": "Ask a question about a public company and get an answer with every claim cited to a specific SEC filing \u2014 then independently verified against the evidence that produced it.",
    "detail": "You send a ticker and a question. The agent writes a research plan, then calls up to four tools against SEC EDGAR \u2014 listing filings, pulling a specific section out of a 10-K, fetching reported XBRL figures, measuring the price move after a filing date. It drafts findings with accession-number citations, and a separate verifier pass re-reads the gathered evidence and checks that each citation actually supports its claim before the answer is returned. Every model and tool call is metered, so each response carries its own token count, dollar cost, and latency.",
    "tech": [
      "Python",
      "FastAPI",
      "MCP",
      "Pydantic",
      "LangGraph",
      "Claude",
      "AWS Bedrock",
      "Redis",
      "Docker",
      "React",
      "TypeScript"
    ],
    "path": "ai-platform-projects/sec-filing-intelligence",
    "tests": 176,
    "highlights": [
      "Multi-provider model access: Anthropic, AWS Bedrock, and a deterministic replay provider behind one interface, switched by config",
      "A verifier node audits every citation against gathered evidence and can mark the answer unverified",
      "Least-privilege capability grants plus a hard tool-call ceiling bound what the agent loop can reach and how long it runs",
      "Telemetry on every model and tool call: tokens, estimated USD, latency percentiles, failure kinds, sliced by model and tool",
      "An eval harness measuring accuracy, consistency, reliability, latency, and cost as separate numbers, because they fail independently",
      "A React UI that streams the agent's run over server-sent events as it happens"
    ],
    "images": [
      {
        "src": "sec-filing-light.png",
        "alt": "The research UI showing the agent's run timeline, quoted filing passages, and cost telemetry"
      },
      {
        "src": "sec-filing-dark.png",
        "alt": "The same research interface in dark mode"
      }
    ],
    "io": {
      "input": "A ticker and a plain-English question \u2014 e.g. AAPL, \"What supply chain risks does Apple disclose?\"",
      "output": "A cited answer plus structured findings, each with an accession number and filing date, a verified/unverified verdict, and the run's token, cost, and latency figures.",
      "scale": "167 tests, all offline. Four tools, three model providers, one MCP server."
    },
    "sources": [
      {
        "label": "SEC EDGAR",
        "url": "https://www.sec.gov/edgar/sec-api-documentation",
        "note": "Company submissions, filing documents, and XBRL company facts."
      },
      {
        "label": "Yahoo Finance",
        "url": "https://finance.yahoo.com/",
        "note": "Daily closes, for measuring the price reaction to a filing."
      }
    ]
  },
  {
    "slug": "earnings-drift-tracker",
    "rank": 6,
    "title": "Earnings Drift Tracker",
    "category": "software-engineering",
    "summary": "Measures whether a stock keeps drifting in the direction of an earnings surprise, by pairing each announcement with the return over the days that followed.",
    "detail": "For each quarterly announcement it takes the gap between reported and estimated EPS, finds the last trading session on or before the announcement, and measures the cumulative return 1, 5, and 10 trading days later. Correlating surprise against drift is the question the project exists to ask. The answer is usually 'weakly, if at all' \u2014 which makes the data-handling choices the substance of it: announcements land on holidays and weekends, recent quarters have no 10-day window yet, and a zero consensus estimate makes the surprise percentage undefined rather than zero.",
    "tech": [
      "Python",
      "pandas",
      "NumPy",
      "REST APIs",
      "pytest"
    ],
    "path": "software-engineer-projects/earnings-drift-tracker",
    "tests": 47,
    "highlights": [
      "Announcements landing on a non-trading day fall back to the prior session's close; requiring an exact index match silently dropped a large, non-random slice of events",
      "A horizon with insufficient history is omitted rather than zero-filled, so a missing return is never read as a flat one",
      "A zero consensus estimate yields an undefined surprise percentage, not 0%, which would bias the correlation toward zero"
    ],
    "io": {
      "input": "A ticker and a date range.",
      "output": "One row per announcement \u2014 surprise percentage and forward returns at each horizon \u2014 plus the correlation between them.",
      "scale": "29 tests. The demo covers 62 companies and 1,959 real announcements."
    },
    "sources": [
      {
        "label": "Yahoo Finance",
        "url": "https://finance.yahoo.com/",
        "note": "Reported vs estimated EPS, and daily closes."
      },
      {
        "label": "Financial Modeling Prep",
        "url": "https://site.financialmodelingprep.com/developer/docs",
        "note": "The CLI's earnings-surprise source; needs a free API key."
      }
    ]
  },
  {
    "slug": "factor-based-portfolio-simulator",
    "rank": 1,
    "title": "Factor Portfolio Simulator",
    "category": "software-engineering",
    "summary": "Backtests a cross-sectional factor strategy the honest way \u2014 scoring each stock only on information that existed on the rebalance date.",
    "detail": "Given daily closes for a universe of stocks, it ranks them at each rebalance on momentum and low-volatility signals computed strictly from prior data, buys the top N equally weighted, and tracks the resulting portfolio value day by day. It then regresses the daily excess returns on the Fama-French three factors to separate genuine alpha from market, size, and value exposure. The correctness question the whole project turns on is temporal: a factor computed even one day into the future turns a flat strategy into a spectacular one.",
    "tech": [
      "Python",
      "pandas",
      "NumPy",
      "statsmodels",
      "yfinance",
      "pytest"
    ],
    "path": "software-engineer-projects/factor-based-portfolio-simulator",
    "tests": 70,
    "highlights": [
      "Fixed a look-ahead bias that overstated total return by 92 percentage points -- factors were computed once from the whole sample and reused at every rebalance",
      "Performance metrics were being computed on the last five rows of the backtest while describing three years",
      "Score-proportional weighting inverted on negative scores, producing short positions in a long-only book",
      "examples/lookahead_demo.py reproduces the biased and corrected loops over identical prices"
    ],
    "output": {
      "caption": "examples/lookahead_demo.py \u2014 identical prices, the only difference is when factors were measured",
      "text": "                       point-in-time   full-sample (bug)\n  total_return                  2.85%              95.43%\n  annualized_return             0.95%              25.25%\n  max_drawdown                 21.12%              16.91%\n  sharpe_ratio                   0.14                1.42\n\n  total return overstated by +92.6%"
    },
    "io": {
      "input": "A list of tickers, a date range, which factors to use, how many names to hold, and how often to rebalance.",
      "output": "A daily NAV path, per-rebalance weights, total and annualized return, volatility, Sharpe, max drawdown, and a Fama-French attribution table.",
      "scale": "52 tests. The bundled demo runs 62 tickers over six years of real daily closes."
    },
    "sources": [
      {
        "label": "Yahoo Finance (via yfinance)",
        "url": "https://finance.yahoo.com/",
        "note": "Daily adjusted closes for the 62-name demo universe."
      },
      {
        "label": "Kenneth French Data Library",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
        "note": "Daily Fama-French factors, for the attribution regression."
      }
    ]
  },
  {
    "slug": "performance-optimization",
    "rank": 4,
    "title": "fastcache \u2014 an O(1) LRU cache",
    "category": "software-engineering",
    "summary": "A drop-in memoization decorator with O(1) lookup, insertion, and eviction, benchmarked against the standard library and against the list-based version it replaced.",
    "detail": "An LRU cache decorator with O(1) lookup, insert, and eviction, plus a general `cached` decorator adding TTL expiry and a choice of eviction policy. The benchmark harness measures the hit path against `functools.lru_cache` and the list-based version this replaced, and measures LRU against LFU across five access patterns \u2014 because neither policy wins everywhere, and shipping one with no evidence it was the right one was the gap.",
    "tech": [
      "Python",
      "threading",
      "pytest",
      "benchmarking"
    ],
    "path": "software-engineer-projects/performance-optimization",
    "tests": 67,
    "highlights": [
      "The original called `list.remove` on every cache hit -- a linear scan on the one path a cache exists to make fast. Across sizes 128 to 32,768 it slows 8.7x while this one stays flat at ~0.45us",
      "Expiry needs no heap: every entry gets the same TTL, so deadline order is insertion order and the next entry to die is the front of the dict",
      "An expired entry must not count as a hit, or the hit rate is inflated by entries that were discarded -- and it still occupies capacity, so eviction now takes a dead entry before a live one",
      "LFU wins the scan-flushes-a-hot-set workload by 11 points; LRU wins the shifting-hot-set workload by 86, because LFU never decays counts and so refuses to admit a new key at all",
      "Under LFU the entry just inserted can be the one evicted, and the code then read it back out of the cache"
    ],
    "output": {
      "caption": "LRU against LFU: 50,000 accesses over 2,000 keys, cache holds 200",
      "text": "workload                 LRU hit  LFU hit    winner\nzipf (skewed)              71.3%    76.4%   LFU +5\nuniform (no locality)      10.1%    10.1%      tie\nsequential scan             0.0%     0.0%      tie\nhot set + scans            14.3%    24.9%  LFU +11\nshifting hot set           96.4%    10.7%  LRU +86"
    },
    "io": {
      "input": "A function to memoise, a max size, optionally a TTL in seconds and a policy (`lru` or `lfu`).",
      "output": "A wrapped function plus hits, misses, evictions, expirations, and hit rate; the benchmark emits microseconds per call and hit rate by workload.",
      "scale": "67 tests. Benchmarked to 32,768 entries, and 50,000 accesses over 2,000 keys."
    }
  },
  {
    "slug": "web-crawler-and-search-engine",
    "rank": 2,
    "title": "Trie Search",
    "category": "software-engineering",
    "summary": "Crawls a website, indexes every word it finds into a prefix tree, and answers prefix and single-character-wildcard queries against it.",
    "detail": "A breadth-first crawler walks a site to a given link depth, strips each page to its visible text, and folds every word into a trie. The trie answers which words look like the query \u2014 by prefix or single-character wildcard \u2014 and a BM25 scorer answers which pages those words make relevant, which the original set-valued index could not: a page mentioning a word once and a directory mentioning it nineteen times were indistinguishable. Each node has 27 children, one per letter plus a bucket for everything else, which is what turns a wildcard query into a bounded walk down the tree instead of a scan across every key.",
    "tech": [
      "Python",
      "httpx",
      "lxml",
      "data structures",
      "pytest"
    ],
    "path": "software-engineer-projects/web-crawler-and-search-engine",
    "tests": 77,
    "highlights": [
      "Search was retrieval without ranking: each word mapped to the set of pages holding it, returned alphabetically, with no way to prefer a page matching both words of a two-word query",
      "BM25's IDF needs a floor at zero -- a term on more than half the pages otherwise scores negative, and a page improves its rank by not matching the query",
      "A wildcard token expands to many terms, so requiring every term to be present would be wrong; the intent is every token, and the two coincide only when each token resolved to one term",
      "Trie.__iter__ yielded (key, value) tuples, which broke keys(), values(), items() and dict(trie) -- the class claimed a contract it failed",
      "Wildcard search matched '*' while every doc promised '?', so all documented examples returned nothing",
      "The visited-URL set was a module-level global, so the second crawl in a process returned nothing"
    ],
    "output": {
      "caption": "Ranked search over a five-page crawl",
      "text": "query 'park'\n  1  /parks-directory   0.650   park x19   82 words\n  2  /park-hours        0.573   park x4    32 words\n  3  /dog-park-rules    0.540   park x5    64 words\n  4  /about             0.422   park x3    86 words\n\n/park-hours beats /dog-park-rules on fewer mentions:\n4 in 32 words is denser than 5 in 64."
    },
    "io": {
      "input": "A start URL and a link depth, then a query: words, `par*` for a prefix, `d?g` for a wildcard.",
      "output": "Pages ranked by BM25, each showing its score and which terms matched how many times. Plus a report of pages that could not be fetched.",
      "scale": "77 tests, no network. Crawl is capped by depth, page count, and a URL allowlist."
    }
  },
  {
    "slug": "card-game-system",
    "rank": 5,
    "title": "Card Game",
    "category": "software-engineering",
    "summary": "A single-player poker-style draw game: you are dealt seven cards, discard up to five, and the resulting hand is scored \u2014 score nothing and the run ends.",
    "detail": "Deals seven cards, takes your discards, draws replacements, and evaluates the hand against an eight-tier table from a pair up to a straight flush. Scoring reads all seven cards rather than the best five, which is where the edge cases live: a flush needs five of a suit anywhere in the hand, two triples make a full house, a pair inside a run does not break the run, and the ace plays both high and low without wrapping. A Monte Carlo advisor then values all 120 legal discards \u2014 enumerating exactly where that is cheap, sampling above it \u2014 and reports which options are indistinguishable rather than ranking noise.",
    "tech": [
      "Python",
      "rich",
      "OOP",
      "pytest"
    ],
    "path": "software-engineer-projects/card-game-system",
    "tests": 114,
    "highlights": [
      "Straights and straight flushes were missing entirely, and a straight is more likely than a flush -- hands that should have scored were ending the run",
      "\"Has a straight and has a flush\" is not a straight flush: 5h 6d 7h 8s 9h Kh 2h holds both and is neither, so the search runs per suit",
      "Six- and seven-card flushes scored as nothing: `5 in suit_counts.values()` is False when you hold six of a suit",
      "Two separate triples scored as three-of-a-kind rather than a full house, worth 100 instead of 250",
      "Dealing from an empty deck returned None, which entered the hand and crashed later in scoring, far from the cause"
    ],
    "output": {
      "caption": "The advisor on four to a royal flush, holding a pair",
      "text": "holding A\u2665 K\u2665 Q\u2665 J\u2665 7\u2663 7\u2660 2\u2666 -> Pair\n  1. discard 7\u2663, 7\u2660, 2\u2666      534.6 pts (\u00b1136), scores 93.0%\n  2. discard 7\u2663, 7\u2660          309.6 pts (exact), scores 84.5%\n  3. discard 7\u2663, 2\u2666          308.9 pts (exact), scores 82.7%\n  5. discard 2\u2666              176.7 pts (exact), scores 100.0%"
    },
    "io": {
      "input": "Your discard choices each round, up to five of the seven cards -- or a hand typed as `Ah Kh Qh Jh 7c 7s 2d` for the advisor to analyse.",
      "output": "A hand rank and points per round with a running total, plus the expected value of every legal discard, labelled exact or sampled.",
      "scale": "114 tests. 120 discards evaluated per recommendation: 45 draws enumerated for one card, 990 for two, sampled above that."
    }
  },
  {
    "slug": "course-catalog-scheduling-system",
    "rank": 3,
    "title": "Course Catalog & Scheduling",
    "category": "software-engineering",
    "summary": "Reads the live University of Chicago MPCS catalog for any quarter, then builds the best conflict-free timetable from it \u2014 rather than only checking one you already wrote down.",
    "detail": "Fetches the real course listing from mpcs-courses.cs.uchicago.edu for any quarter back to 2015-16, then answers the question a filter cannot: given the courses you need and the hours you refuse, what are your options? A branch-and-bound search returns the best conflict-free schedules, scoring preferences in one interpretable unit \u2014 minutes of annoyance. Sections are alternatives, not additions: two sections of one course are the same course at two times, so picking which one is most of the value and no filter over the catalogue can do it. The search also reports whether its answer is proven optimal or merely the best it had time to find.",
    "tech": [
      "Python",
      "httpx",
      "csv",
      "interval logic",
      "pytest"
    ],
    "path": "software-engineer-projects/course-catalog-scheduling-system",
    "tests": 145,
    "highlights": [
      "The bundled CSV was a snapshot, so it went stale the moment the department published a new quarter -- it now reads the live catalog, and a script regenerates the offline snapshot",
      "A quarter is published before its meeting times are set. Winter 2026-27 went up with all 30 courses and no times -- and a course with no time conflicts with nothing, so it scores zero and beats every real timetable. Left in, the best schedule is the one that schedules nothing",
      "`build_schedule` checked times and nothing else, and two sections of one course deliberately do not overlap -- so it enrolled you in Algorithms twice, under two different instructors",
      "The time parser rejected `6pm` as malformed, with a test asserting it. The real listing writes `Monday 6pm - 8pm` beside `Monday 5:30pm - 8:30pm`, so it was dropping real courses",
      "Two weekly meetings are one table cell split by `<br/>`; stripping tags first glues `3:20pm` to `Thursday` and parses as nothing",
      "Gaps are not monotone: inserting a class into an idle afternoon reduces total gap time, so a bound that assumed gaps only grow would prune the gap-filling schedule, which is usually the best one",
      "Prefix search was actually substring search, so `\"530\"` matched `MPCS 53014-1` via the digits in the middle of the number"
    ],
    "output": {
      "caption": "Four courses from the live Autumn 2026-27 listing, nothing before 10am, Friday and the weekend free",
      "text": "32 course(s) from Autumn 2026-27, live from the department.\n\n1. MPCS 55001-1, MPCS 51042-1, MPCS 51046-1, MPCS 53001-1\n  cost 145\n    Tue  11:00-12:20 MPCS 51042-1, 17:30-20:30 MPCS 55001-1\n    Wed  14:00-17:00 MPCS 51046-1, 17:30-20:30 MPCS 53001-1\n    why: extra_days 120, gaps 25\n\nsearched 320 nodes"
    },
    "io": {
      "input": "A quarter (`2026-27/winter`, or `current`), plus either a search -- code prefix, keyword, day -- or a request: how many courses, which are required, which days to keep free, nothing before a given time.",
      "output": "Matching courses, or the best conflict-free schedules ranked by cost with the penalty that drove each, how many courses were set aside for having no published time, the nodes searched, and whether optimality was proven.",
      "scale": "145 tests, all offline: the real listing pages are saved as fixtures and the transport is faked. 48 quarters available live; a 30-course quarter searches in a few hundred nodes."
    },
    "sources": [
      {
        "label": "UChicago MPCS course catalog",
        "url": "https://mpcs-inforstems.uchicago.edu/",
        "note": "A 30-course snapshot, bundled with the package as CSV."
      }
    ]
  },
  {
    "slug": "bitcoin-and-asset-trading",
    "title": "Bitcoin Price Forecasting",
    "category": "data-science",
    "summary": "Forecasts Bitcoin prices with a stacked LSTM trained on rolling 60-day windows, built from minute-resolution trade data resampled to daily bars.",
    "detail": "Takes a 127 MB file of minute-by-minute BTC/USD trades, resamples it to daily OHLCV, scales it, and cuts it into overlapping fixed-length sequences so a recurrent network can learn from the ordering rather than treating each day independently. The model is an LSTM stack with dropout between layers and dense layers on top. The hard part of a pipeline like this is not the architecture \u2014 it is the sequence construction: scale before the split and the test set leaks into training, window carelessly and the model reads its own answer.",
    "tech": [
      "Python",
      "TensorFlow",
      "Keras",
      "LSTM",
      "NumPy",
      "pandas",
      "scikit-learn"
    ],
    "path": "data-science-projects/bitcoin-and-asset-trading",
    "rank": 3,
    "io": {
      "input": "Minute-resolution BTC/USD trade history, a lookback window, and a forecast horizon.",
      "output": "A trained model plus predicted-versus-actual price paths on a held-out period.",
      "scale": "127 MB of raw trades resampled to daily bars; 60-day lookback sequences."
    },
    "sources": [
      {
        "label": "Bitcoin Historical Data (Kaggle)",
        "url": "https://www.kaggle.com/datasets/mczielinski/bitcoin-historical-data",
        "note": "Minute-resolution BTC/USD trades, resampled to daily bars."
      }
    ]
  },
  {
    "slug": "fake-news-detection",
    "title": "Fake News Detection",
    "category": "data-science",
    "summary": "Classifies news articles as fake or real, comparing several models across text features and article metadata \u2014 and finding that the metadata alone carries no usable signal.",
    "detail": "Builds features three ways: TF-IDF over the article text, sentiment polarity, and structural metadata such as word count, readability and whether the piece carries images or video. Several classifiers are compared under cross-validation. The result worth reporting is negative: a model trained on metadata alone scores an ROC AUC of 0.46, at or below a coin flip, so none of those structural signals distinguish a fake article in this dataset. Its accuracy of 46.5% looks respectable until you notice the classes are split almost evenly.",
    "tech": [
      "Python",
      "scikit-learn",
      "XGBoost",
      "TF-IDF",
      "TextBlob",
      "pandas",
      "seaborn"
    ],
    "path": "data-science-projects/fake-news-detection",
    "rank": 4,
    "io": {
      "input": "4,000 labelled articles with title, body, author, source and structural metadata.",
      "output": "Per-model accuracy, ROC AUC and confusion matrices, plus feature importances.",
      "scale": "4,000 articles, 50.6% labelled fake. 39 code cells."
    },
    "sources": [
      {
        "label": "Fake News Detection (Kaggle)",
        "url": "https://www.kaggle.com/datasets/khushikyad001/fake-news-detection",
        "note": "4,000 rows. Synthetic: titles are 'Breaking News N' and labels appear randomly assigned."
      }
    ]
  },
  {
    "slug": "customer-churn-prediction",
    "title": "Customer Churn Prediction",
    "category": "data-science",
    "summary": "Telco churn treated as what it actually is \u2014 right-censored survival data driving a spending decision \u2014 rather than a binary score. Kaplan-Meier, the log-rank test and Cox regression from scratch, checked against statsmodels.",
    "detail": "73.5% of these 7,043 customers had not left when the data was cut, so their lifetime is not \"no churn\" but *at least* their current tenure \u2014 and a classifier reads a one-month customer who stayed and a six-year customer who stayed as the same row. Survival analysis uses them properly: the median lifetime turns out to be undefined (more than half are still subscribed), the restricted mean says 46.8 of the next 60 months, and the Cox model reaches a concordance of 0.870 against the classifier's 0.845 AUC on the same rows. It then turns the score into a decision, because a churn model retains nobody: the optimal cut-off given a $30 offer is 0.25 rather than 0.5, and ranking by probability \u00d7 value returns 33% more than ranking by probability for the same budget \u2014 which needs expected remaining months, something only the survival model has.",
    "tech": [
      "Python",
      "NumPy",
      "pandas",
      "scikit-learn",
      "statsmodels",
      "pytest"
    ],
    "path": "data-science-projects/customer-churn-prediction",
    "rank": 1,
    "io": {
      "input": "The Telco CSV, plus the campaign economics: cost per offer, acceptance rate, margin, and horizon -- all arguments, because none of them can be read off the dataset.",
      "output": "Survival curves with confidence bands, hazard ratios with intervals and an assumption test, cross-validated AUC with bootstrap intervals, calibration error, and the expected value of every targeting threshold.",
      "scale": "7,043 customers, 73.5% censored. 58 tests; statsmodels is a test dependency only, used to check the from-scratch estimators to 1e-8."
    },
    "sources": [
      {
        "label": "Telco Customer Churn (Kaggle)",
        "url": "https://www.kaggle.com/datasets/blastchar/telco-customer-churn",
        "note": "7,043 customers; the notebook drops 11 rows with blank TotalCharges."
      }
    ],
    "tests": 58,
    "highlights": [
      "The dataset is right-censored survival data and the notebook treated it as binary classification, discarding the timing information entirely -- the Cox model's concordance (0.870) beats the classifier's AUC (0.845) on the same rows",
      "Class rebalancing -- SMOTE, which the notebook used -- changed the ranking by 0.0001 of AUC and made the probabilities twice too large: calibration error 0.149 against 0.012 unweighted. AUC cannot see it, and it matters the moment a score is multiplied by money",
      "The leak everyone names was worth +0.0002 of AUC. Reporting one lucky 80/20 split as an estimate was worth 0.017, and 0.8617 sits outside the interval cross-validation supports",
      "`roc_curve(y_test_numeric, y_prob)` referenced a variable assigned nowhere in the notebook -- ruff reports F821 twice, plus three undefined `np`",
      "Eleven customers with a blank TotalCharges were filled with the column mean, $2,283. All eleven have tenure 0: they have never been billed, so the answer is exactly 0 and it is derivable",
      "Six one-hot columns were exact duplicates of another column (\"No internet service\" is the same 1,526 customers as InternetService=No), leaving the design matrix at rank 21 of 27 and the Cox Hessian singular",
      "The proportional-hazards assumption fails for 16 of 20 covariates, so the hazard ratios are time-averages -- reported next to the table rather than in a footnote"
    ],
    "output": {
      "caption": "Survival, and the same budget spent three ways",
      "text": "  S( 6 months) = 0.885   95% CI [0.877, 0.892]\n  S(24 months) = 0.789   95% CI [0.778, 0.799]\n  S(60 months) = 0.664   95% CI [0.650, 0.678]\n  median lifetime: never reached inside the window\n  concordance 0.870  vs classifier AUC 0.845\n\n  same budget of 1,000 calls:\n    by_expected_value    $61,496\n    by_probability       $46,317\n    everyone             $ 5,602\n    random               $ 1,172"
    }
  },
  {
    "slug": "global-security-threats",
    "title": "Cybersecurity Threat Analysis",
    "category": "data-science",
    "summary": "Finds structure in a decade of global cyber incidents using six unsupervised methods \u2014 clustering, dimensionality reduction and anomaly detection \u2014 with no labels to check against.",
    "detail": "Three thousand incidents from 2015 to 2024, each with financial loss, users affected, resolution time, attack type, target industry and defence mechanism. The numeric fields are standardised and projected with PCA and t-SNE, grouped with K-Means and DBSCAN, and screened for outliers with Isolation Forest and Local Outlier Factor. Unsupervised work is harder to judge than it looks: there is no ground truth, so a clean-looking separation can be an artifact of feeding the clusterer the same columns the projection used. The demo says where that applies.",
    "tech": [
      "Python",
      "scikit-learn",
      "PCA",
      "t-SNE",
      "K-Means",
      "DBSCAN",
      "Isolation Forest",
      "seaborn"
    ],
    "path": "data-science-projects/global-security-threats",
    "rank": 6,
    "io": {
      "input": "3,000 incident records with loss, users affected, resolution time and categorical attributes.",
      "output": "Cluster assignments, a 2-D projection, and a flagged set of anomalous incidents.",
      "scale": "3,000 incidents, 2015\u20132024, 6 attack types, 150 flagged anomalous."
    },
    "sources": [
      {
        "label": "Global Cybersecurity Threats 2015-2024 (Kaggle)",
        "url": "https://www.kaggle.com/datasets/atharvasoundankar/global-cybersecurity-threats-2015-2024",
        "note": "3,000 incidents across 7 industries and 6 attack types."
      }
    ]
  },
  {
    "slug": "personalized-recommendations-for-e-commerce",
    "title": "E-commerce Recommendations",
    "category": "data-science",
    "summary": "Recommends products by joining customer behaviour against a product catalogue, spanning boosting, ensembles, text features and seasonality in one pipeline.",
    "detail": "Two 10,000-row tables \u2014 customers with browsing history, purchase history, segment and average order value, and products with category, brand, price, rating and review sentiment. The pipeline encodes both sides, derives features from the text and seasonal fields, and compares gradient-boosted and ensemble models under cross-validation. The first thing the data shows is awkward for the premise: the three customer segments are near-evenly sized and barely differ in average order value, so the segment label carries little signal and the recommender has to lean on behaviour instead.",
    "tech": [
      "Python",
      "scikit-learn",
      "XGBoost",
      "pandas",
      "recommender systems"
    ],
    "path": "data-science-projects/personalized-recommendations-for-e-commerce",
    "rank": 5,
    "io": {
      "input": "A customer's browsing and purchase history, segment, season, and the product catalogue.",
      "output": "Ranked product recommendations, with model comparison across the candidate approaches.",
      "scale": "10,000 customers \u00d7 10,000 products, 3 segments."
    },
    "sources": [
      {
        "label": "Personalized Recommendations for E-Commerce (Kaggle)",
        "url": "https://www.kaggle.com/datasets/suvroo/personalized-recommendations-for-e-commerce",
        "note": "Two 10,000-row tables: customer behaviour and product catalogue."
      }
    ]
  },
  {
    "slug": "stock-bond-portfolio-analysis",
    "title": "Stock-Bond Portfolio Optimisation",
    "category": "data-science",
    "summary": "Allocates across five ETFs by solving a constrained optimisation whose objective trades factor-risk exposure against Sharpe, with the weights informed by a regression and conditioned on the volatility regime.",
    "detail": "Pulls twelve years of daily prices for SPY, IWM, TLT, LQD and SHV, decomposes each asset's returns against a set of risk factors, and runs a SciPy constrained optimisation over portfolio weights. The objective is not textbook mean-variance: it blends factor-risk alignment with a Sharpe term whose weight is swept across twelve values, so you can see how the allocation shifts as the investor's priority moves from risk-matching to return-seeking. Factor weights are adjusted from the regression output, and VIX is carried alongside as a volatility-regime signal.",
    "tech": [
      "Python",
      "pandas",
      "NumPy",
      "SciPy",
      "statsmodels",
      "yfinance",
      "portfolio theory"
    ],
    "path": "data-science-projects/stock-bond-portfolio-analysis",
    "rank": 2,
    "io": {
      "input": "Five ETF tickers, a date range, and a client risk profile expressed as target factor weights.",
      "output": "Optimal portfolio weights per Sharpe preference, the factor exposures they imply, and realised performance over the period.",
      "scale": "463 lines, the largest analysis here. 5 assets, 2012\u20132024 daily."
    },
    "sources": [
      {
        "label": "Yahoo Finance (via yfinance)",
        "url": "https://finance.yahoo.com/",
        "note": "Daily prices for SPY, IWM, TLT, LQD and SHV, 2012-2024."
      },
      {
        "label": "Kenneth French Data Library",
        "url": "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html",
        "note": "Fama-French factor returns."
      },
      {
        "label": "FRED",
        "url": "https://fred.stlouisfed.org/",
        "note": "Interest-rate and liquidity indicators."
      }
    ]
  },
  {
    "slug": "weather-trends-and-forecast",
    "title": "Weather Trends & Forecast",
    "category": "data-science",
    "summary": "Pulls decades of hourly reanalysis weather data from the Open-Meteo ERA5 API, extracts long-run temperature trends, and projects them forward.",
    "detail": "Scripts rather than a notebook: one downloads and caches from the ERA5 archive for a given latitude and longitude, one computes descriptive statistics and resamples to the period of interest, and one fits a linear trend and extrapolates. Note one honest caveat \u2014 a legislation-influence feature in the forecast is synthetic, generated rather than sourced, so it demonstrates the mechanism rather than measuring a real effect.",
    "tech": [
      "Python",
      "pandas",
      "scikit-learn",
      "requests",
      "matplotlib",
      "time series"
    ],
    "path": "data-science-projects/weather-trends-and-forecast",
    "rank": 7,
    "io": {
      "input": "A latitude and longitude, plus a date range.",
      "output": "Cleaned historical series, descriptive statistics, a fitted trend, and a forward projection.",
      "scale": "Hourly ERA5 reanalysis. 3 scripts, ~200 lines."
    },
    "sources": [
      {
        "label": "Open-Meteo ERA5 archive API",
        "url": "https://open-meteo.com/en/docs/historical-weather-api",
        "note": "Hourly reanalysis by latitude and longitude. The README also cites Meteostat; the code calls Open-Meteo."
      }
    ]
  }
];
