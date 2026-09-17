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
    "summary": "A multi-agent research platform over SEC EDGAR filings, served as both an HTTP API and an MCP server, with per-call token, cost, and latency telemetry.",
    "detail": "Ask a question about a public company. The agent plans the research, pulls the filings and XBRL financials it needs from SEC EDGAR, drafts a cited answer, then runs a separate verification pass that checks every citation against the evidence it actually gathered before returning it. The whole test suite runs offline against a replay provider, so CI exercises the real agent graph with no API key and no spend.",
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
    ]
  },
  {
    "slug": "earnings-drift-tracker",
    "rank": 5,
    "title": "Earnings Drift Tracker",
    "category": "software-engineering",
    "summary": "Measures post-earnings-announcement drift against the size of the analyst surprise, and correlates the two.",
    "detail": "Pulls earnings surprises from Financial Modeling Prep and daily closes from Yahoo Finance, then measures how far a stock moves over the 1, 5, and 10 trading days after each announcement. The computation layer is pure -- no network, no printing -- which is what makes the arithmetic directly testable.",
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
    ]
  },
  {
    "slug": "factor-based-portfolio-simulator",
    "rank": 1,
    "title": "Factor Portfolio Simulator",
    "category": "software-engineering",
    "summary": "A point-in-time backtest of cross-sectional equity factor strategies, with Fama-French 3-factor attribution.",
    "detail": "Ranks a universe on value, momentum, size, and low-volatility signals, holds the top N, rebalances on a fixed cadence, and attributes the result against the Fama-French factors. The important property is point-in-time exposure: at each rebalance, factors are computed only from data available on that date.",
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
    }
  },
  {
    "slug": "performance-optimization",
    "rank": 6,
    "title": "fastcache \u2014 an O(1) LRU cache",
    "category": "software-engineering",
    "summary": "An LRU cache decorator in pure Python, benchmarked against functools and against the list-based approach it replaced.",
    "detail": "The original tracked recency in a list and called list.remove on every cache hit -- a linear scan on the one path a cache exists to make fast. This version keeps recency in the dict's insertion order, so lookup, insert, and eviction are all O(1). The benchmark runs all three implementations side by side.",
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
    }
  },
  {
    "slug": "web-crawler-and-search-engine",
    "rank": 2,
    "title": "Trie Search",
    "category": "software-engineering",
    "summary": "Crawls a website, indexes every word into a trie, and searches it by prefix or single-character wildcard.",
    "detail": "A breadth-first crawler feeding a trie that implements the full MutableMapping interface. Each node has 27 children -- one per letter plus a bucket for everything else -- which is a lossy folding that keeps wildcard search a bounded walk rather than a scan.",
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
    }
  },
  {
    "slug": "card-game-system",
    "rank": 4,
    "title": "Card Game",
    "category": "software-engineering",
    "summary": "A single-player poker-style draw game: seven cards, discard up to five, score the hand.",
    "detail": "Rules, scoring, and display are separated, so a test can play twelve full rounds without a terminal. The scorer evaluates all seven cards rather than the best five.",
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
    }
  },
  {
    "slug": "course-catalog-scheduling-system",
    "rank": 3,
    "title": "Course Catalog & Scheduling",
    "category": "software-engineering",
    "summary": "Searches a university course catalog and builds a schedule that does not double-book you.",
    "detail": "A meeting is a day plus a half-open minute interval. Half-open is the whole conflict rule: a class ending at 7:30pm and another starting at 7:30pm are back to back, not a conflict, and a closed interval would reject a valid schedule.",
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
    }
  },
  {
    "slug": "bitcoin-and-asset-trading",
    "title": "Bitcoin Price Forecasting",
    "category": "data-science",
    "summary": "An LSTM forecasting Bitcoin prices from 60-day lookback sequences.",
    "detail": "A full deep-learning pipeline: MinMax scaling, sequence windowing, dropout regularisation, and evaluation against a held-out period.",
    "tech": [
      "Python",
      "TensorFlow",
      "Keras",
      "NumPy",
      "pandas",
      "scikit-learn"
    ],
    "path": "data-science-projects/bitcoin-and-asset-trading"
  },
  {
    "slug": "fake-news-detection",
    "title": "Fake News Detection",
    "category": "data-science",
    "summary": "Classifies news articles using metadata, sentiment, and TF-IDF features.",
    "detail": "Feature engineering across article metadata and text, compared across several classifiers with an emphasis on which features actually carry signal.",
    "tech": [
      "Python",
      "scikit-learn",
      "XGBoost",
      "pandas",
      "TextBlob",
      "seaborn"
    ],
    "path": "data-science-projects/fake-news-detection"
  },
  {
    "slug": "customer-churn-prediction",
    "title": "Customer Churn Prediction",
    "category": "data-science",
    "summary": "Predicts telecom customer churn, with exploration, training, and evaluation.",
    "detail": "An end-to-end supervised pipeline on the Telco churn dataset, from exploratory analysis through model comparison and threshold selection.",
    "tech": [
      "Python",
      "scikit-learn",
      "pandas",
      "seaborn",
      "matplotlib"
    ],
    "path": "data-science-projects/customer-churn-prediction"
  },
  {
    "slug": "global-security-threats",
    "title": "Cybersecurity Threat Analysis",
    "category": "data-science",
    "summary": "Clustering and anomaly detection over global cyber incidents, 2015-2024.",
    "detail": "Unsupervised analysis to surface attack patterns and outliers: dimensionality reduction with PCA and t-SNE, clustering with K-Means and DBSCAN, and anomaly detection with Isolation Forest and Local Outlier Factor.",
    "tech": [
      "Python",
      "scikit-learn",
      "PCA",
      "t-SNE",
      "K-Means",
      "DBSCAN",
      "Isolation Forest"
    ],
    "path": "data-science-projects/global-security-threats"
  },
  {
    "slug": "personalized-recommendations-for-e-commerce",
    "title": "E-commerce Recommendations",
    "category": "data-science",
    "summary": "A recommender over customer behaviour and product catalogue data.",
    "detail": "Builds personalised product recommendations by joining customer interaction history against the product catalogue.",
    "tech": [
      "Python",
      "pandas",
      "scikit-learn",
      "recommender systems"
    ],
    "path": "data-science-projects/personalized-recommendations-for-e-commerce"
  },
  {
    "slug": "stock-bond-portfolio-analysis",
    "title": "Stock-Bond Portfolio Optimisation",
    "category": "data-science",
    "summary": "Optimises a stock-bond allocation across timeframes and risk levels.",
    "detail": "Mean-variance style analysis of stock and bond mixes, examining how the efficient allocation shifts with horizon and investor risk tolerance.",
    "tech": [
      "Python",
      "pandas",
      "NumPy",
      "matplotlib",
      "portfolio theory"
    ],
    "path": "data-science-projects/stock-bond-portfolio-analysis"
  },
  {
    "slug": "weather-trends-and-forecast",
    "title": "Weather Trends & Forecast",
    "category": "data-science",
    "summary": "Processes historical weather data to find long-run trends and forecast forward.",
    "detail": "Ingests and cleans a large historical weather dataset, then surfaces multi-decade trends and produces forward forecasts.",
    "tech": [
      "Python",
      "pandas",
      "matplotlib",
      "requests",
      "time series"
    ],
    "path": "data-science-projects/weather-trends-and-forecast"
  }
];
