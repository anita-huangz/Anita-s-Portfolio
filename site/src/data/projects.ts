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
    "tests": 167,
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
    }
  },
  {
    "slug": "earnings-drift-tracker",
    "rank": 5,
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
    "tests": 29,
    "highlights": [
      "Announcements landing on a non-trading day fall back to the prior session's close; requiring an exact index match silently dropped a large, non-random slice of events",
      "A horizon with insufficient history is omitted rather than zero-filled, so a missing return is never read as a flat one",
      "A zero consensus estimate yields an undefined surprise percentage, not 0%, which would bias the correlation toward zero"
    ],
    "io": {
      "input": "A ticker and a date range.",
      "output": "One row per announcement \u2014 surprise percentage and forward returns at each horizon \u2014 plus the correlation between them.",
      "scale": "29 tests. The demo covers 62 companies and 1,959 real announcements."
    }
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
    "tests": 52,
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
    }
  },
  {
    "slug": "performance-optimization",
    "rank": 6,
    "title": "fastcache \u2014 an O(1) LRU cache",
    "category": "software-engineering",
    "summary": "A drop-in memoization decorator with O(1) lookup, insertion, and eviction, benchmarked against the standard library and against the list-based version it replaced.",
    "detail": "Wraps a function so repeated calls with the same arguments return a stored result, evicting the least recently used entry once the cache is full. Recency is tracked in the dictionary's own insertion order, so promoting a key on a hit is a delete-and-reinsert rather than a scan. The argument key folds in each value's type, because 1, 1.0 and True are all equal in Python and would otherwise share one entry. It is thread-safe, and the wrapped function is deliberately called outside the lock so one slow call cannot block every other reader.",
    "tech": [
      "Python",
      "threading",
      "pytest",
      "benchmarking"
    ],
    "path": "software-engineer-projects/performance-optimization",
    "tests": 24,
    "highlights": [
      "The list-based hit path slows 8.5x from a 128-entry cache to 32,768; this one stays flat at ~0.45us",
      "Thread-safe, with the wrapped function called outside the lock so a slow call does not block every reader",
      "1, 1.0 and True no longer share a cache entry -- they are all == in Python, which broke any function branching on type",
      "Exceptions are not cached, so a failed call is retried rather than memoised as a permanent failure"
    ],
    "output": {
      "caption": "fastcache-bench \u2014 20,000 calls, best of 5, microseconds per call",
      "text": "20,000 calls, best of 5. Microseconds per call.\n\n                 HIT PATH (us/call)                  MISS PATH        \n  size   fastcache  functools   list-based   fastcache   functools\n------------------------------------------------------------------------------\n   128       0.420      0.033        0.520       0.671       0.070\n  1024       0.458      0.042        0.648       0.856       0.070\n  8192       0.446      0.044        1.187       1.203       0.071\n 32768       0.470      0.045        4.422       0.663       0.070\n\nfastcache and functools stay flat as the cache grows. The list-based\nrecency tracking -- what this project used to do -- climbs, because every\nhit scans the recency list.\nOver this sweep the list-based hit path got 8.5x slower while fastcache stayed flat.\n\n(functools.lru_cache is C. Matching it in Python is not the goal;\n growing with n is the thing to avoid.)"
    },
    "io": {
      "input": "Any function, plus a maximum cache size.",
      "output": "The same function, memoized, with hit/miss counters, a hit rate, and the current LRU ordering exposed for inspection.",
      "scale": "24 tests. Benchmarks show the list-based approach slowing 8.5x across cache sizes where this stays flat."
    }
  },
  {
    "slug": "web-crawler-and-search-engine",
    "rank": 2,
    "title": "Trie Search",
    "category": "software-engineering",
    "summary": "Crawls a website, indexes every word it finds into a prefix tree, and answers prefix and single-character-wildcard queries against it.",
    "detail": "A breadth-first crawler walks a site to a given link depth, strips each page to its visible text, and folds every word into a trie that maps it to the set of pages it appeared on. The trie is a full MutableMapping, so it behaves like a dict, and each node has 27 children \u2014 one per letter plus a bucket for everything else. That fixed small alphabet is the design trade: it makes the index case-insensitive and lossy about punctuation, but it turns a wildcard query into a bounded walk down the tree instead of a scan across every key.",
    "tech": [
      "Python",
      "httpx",
      "lxml",
      "data structures",
      "pytest"
    ],
    "path": "software-engineer-projects/web-crawler-and-search-engine",
    "tests": 58,
    "highlights": [
      "Trie.__iter__ yielded (key, value) tuples, which broke keys(), values(), items() and dict(trie) -- the class claimed a contract it failed",
      "Wildcard search matched '*' while every doc promised '?', so all documented examples returned nothing",
      "The visited-URL set was a module-level global, so the second crawl in a process returned nothing",
      "HTML extraction glued adjacent elements together, turning <a>C</a><p>alpha</p> into 'Calpha' and losing both words"
    ],
    "output": {
      "caption": "A crawl of a four-page test site, then prefix and wildcard search",
      "text": "Crawled 4 pages, 22 words.\nIndexed 18 distinct words.\n\nprefix search  'par'\n  park           3 page(s)\n  parking        1 page(s)\n  parks          1 page(s)\n  participate    1 page(s)\n  partner        1 page(s)\n\nwildcard       'par?'\n  park           3 page(s)"
    },
    "io": {
      "input": "A start URL and a link depth, then a query like `park` or `c?t`.",
      "output": "For each matching word, the set of pages it appeared on. Plus a report of pages that could not be fetched.",
      "scale": "58 tests, no network. Crawl is capped by depth, page count, and a URL allowlist."
    }
  },
  {
    "slug": "card-game-system",
    "rank": 4,
    "title": "Card Game",
    "category": "software-engineering",
    "summary": "A single-player poker-style draw game: you are dealt seven cards, discard up to five, and the resulting hand is scored \u2014 score nothing and the run ends.",
    "detail": "Deals seven cards, takes your discards, draws replacements, and evaluates the hand against a six-tier scoring table from a pair up to four of a kind. Scoring reads all seven cards rather than the best five, which is where the interesting edge cases live: a flush needs five of a suit anywhere in the hand, and two separate triples make a full house. Rules, scoring, and display are separate, so a test can play a dozen rounds without a terminal.",
    "tech": [
      "Python",
      "rich",
      "OOP",
      "pytest"
    ],
    "path": "software-engineer-projects/card-game-system",
    "tests": 48,
    "highlights": [
      "Six- and seven-card flushes scored as nothing: `5 in suit_counts.values()` is False when you hold six of a suit",
      "Two separate triples scored as three-of-a-kind rather than a full house, worth 100 instead of 250",
      "Dealing from an empty deck returned None, which entered the hand and crashed later in scoring, far from the cause"
    ],
    "output": {
      "caption": "The scorer on four representative hands",
      "text": "  2\u2665 2\u2660 2\u2663 5\u2665 5\u2660 5\u2663 9\u2666               -> FullHouse    250\n  2\u2665 4\u2665 6\u2665 8\u2665 10\u2665 Q\u2665 3\u2660              -> Flush        200\n  2\u2665 2\u2660 5\u2663 5\u2665 8\u2666 9\u2663 K\u2660               -> 2Pair         50\n  2\u2665 4\u2660 6\u2663 8\u2665 10\u2666 Q\u2663 K\u2660              -> None           0"
    },
    "io": {
      "input": "Your discard choices each round, up to five of the seven cards.",
      "output": "A hand rank and points per round, and a running total until a hand fails to score.",
      "scale": "48 tests. The deck recycles discards so a long run never stalls."
    }
  },
  {
    "slug": "course-catalog-scheduling-system",
    "rank": 3,
    "title": "Course Catalog & Scheduling",
    "category": "software-engineering",
    "summary": "Searches a university course catalog and tells you which courses still fit around the ones you have already enrolled in.",
    "detail": "Loads a catalog from CSV, parsing each course's meeting times into days and minute intervals. Search works by course-code prefix or by keyword across titles and instructors, and any search can be filtered against a schedule you are already holding so conflicting options never appear. A meeting is modelled as a half-open interval, which is the entire conflict rule: a class ending at 7:30pm and another starting at 7:30pm are back to back, and treating that as a clash would reject a perfectly valid timetable.",
    "tech": [
      "Python",
      "csv",
      "interval logic",
      "pytest"
    ],
    "path": "software-engineer-projects/course-catalog-scheduling-system",
    "tests": 52,
    "highlights": [
      "Prefix search was actually substring search, so '530' matched 'MPCS 53014-1' via digits in the middle of the number",
      "The default CSV path resolved to a directory that did not exist, so the default argument could never load",
      "Malformed times parsed into plausible-looking numbers instead of raising, silently misplacing a class"
    ],
    "output": {
      "caption": "Searching within an existing schedule; conflicts are filtered out",
      "text": "Enrolled (1):\n  MPCS 53112-1: Advanced Data Analytics (Wed 17:30-20:30)\n\n3 course(s) \u2014 code ~ 'MPCS 530':\n  MPCS 53014-1: Big Data Application Architecture (Mon 17:30-20:30)\n  MPCS 53001-1: Databases (Tue 17:30-20:30)\n  MPCS 53001-2: Databases (Thu 17:30-20:30)"
    },
    "io": {
      "input": "A catalog CSV, a search term, and optionally the course codes you are already enrolled in.",
      "output": "Matching courses with their meeting times, conflicts excluded \u2014 or a named clash if you try to build an impossible schedule.",
      "scale": "52 tests. Ships with a 30-course MPCS catalog."
    }
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
    "rank": 2,
    "io": {
      "input": "Minute-resolution BTC/USD trade history, a lookback window, and a forecast horizon.",
      "output": "A trained model plus predicted-versus-actual price paths on a held-out period.",
      "scale": "127 MB of raw trades resampled to daily bars; 60-day lookback sequences."
    }
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
    "rank": 3,
    "io": {
      "input": "4,000 labelled articles with title, body, author, source and structural metadata.",
      "output": "Per-model accuracy, ROC AUC and confusion matrices, plus feature importances.",
      "scale": "4,000 articles, 50.6% labelled fake. 39 code cells."
    }
  },
  {
    "slug": "customer-churn-prediction",
    "title": "Customer Churn Prediction",
    "category": "data-science",
    "summary": "Predicts which telecom customers will leave, and shows why accuracy is the wrong headline number when only a quarter of them do.",
    "detail": "A supervised pipeline over 7,032 Telco customers: encode the contract, service and billing fields, train and compare classifiers under cross-validation, and inspect what drives the prediction. It reaches an ROC AUC of 0.83, but recall at the default threshold is 49.7% \u2014 it catches about half the customers who actually left. The 78.9% accuracy is close to what you would score by predicting nobody churns. The strongest pattern in the data needs no model at all: month-to-month customers churn at 42.7% against 2.9% on a two-year contract.",
    "tech": [
      "Python",
      "scikit-learn",
      "pandas",
      "seaborn",
      "matplotlib"
    ],
    "path": "data-science-projects/customer-churn-prediction",
    "rank": 6,
    "io": {
      "input": "7,032 customers with contract type, tenure, services, and billing fields.",
      "output": "Churn probability per customer, plus ROC, confusion matrix and feature importances.",
      "scale": "7,032 customers, 26.6% churned. AUC 0.83, recall 49.7%."
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
    "rank": 5,
    "io": {
      "input": "3,000 incident records with loss, users affected, resolution time and categorical attributes.",
      "output": "Cluster assignments, a 2-D projection, and a flagged set of anomalous incidents.",
      "scale": "3,000 incidents, 2015\u20132024, 6 attack types, 150 flagged anomalous."
    }
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
    "rank": 4,
    "io": {
      "input": "A customer's browsing and purchase history, segment, season, and the product catalogue.",
      "output": "Ranked product recommendations, with model comparison across the candidate approaches.",
      "scale": "10,000 customers \u00d7 10,000 products, 3 segments."
    }
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
    "rank": 1,
    "io": {
      "input": "Five ETF tickers, a date range, and a client risk profile expressed as target factor weights.",
      "output": "Optimal portfolio weights per Sharpe preference, the factor exposures they imply, and realised performance over the period.",
      "scale": "463 lines, the largest analysis here. 5 assets, 2012\u20132024 daily."
    }
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
    }
  }
];
