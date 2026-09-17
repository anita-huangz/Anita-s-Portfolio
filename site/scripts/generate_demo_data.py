"""Generate the JSON the interactive demos run on.

Everything here is produced by importing the projects themselves, never by
reimplementing them. Two kinds of output:

  * **data** the browser needs (prices, earnings, the course catalogue)
  * **golden fixtures** — inputs paired with the answer the Python produced,
    which the TypeScript ports are tested against. A port that drifts from the
    Python fails a test instead of quietly disagreeing with it.

    python site/scripts/generate_demo_data.py
"""

from __future__ import annotations

import json
import sys
import warnings
from datetime import date
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "site" / "src" / "data" / "demos"

for project in [
    "software-engineer-projects/earnings-drift-tracker",
    "software-engineer-projects/factor-based-portfolio-simulator",
    "software-engineer-projects/course-catalog-scheduling-system",
    "software-engineer-projects/card-game-system",
    "software-engineer-projects/web-crawler-and-search-engine",
]:
    sys.path.insert(0, str(ROOT / project / "src"))

# A broad, liquid, multi-sector universe. Breadth is the point: factor
# rotation is only interesting when the names do not all move together, and a
# tech-only list makes every factor look the same.
SECTORS: dict[str, list[str]] = {
    "Technology": [
        "AAPL",
        "MSFT",
        "GOOGL",
        "AMZN",
        "META",
        "NVDA",
        "AVGO",
        "ORCL",
        "CRM",
        "ADBE",
        "AMD",
        "INTC",
        "CSCO",
        "QCOM",
        "TXN",
        "IBM",
        "NOW",
        "INTU"
    ],
    "Financials": [
        "JPM",
        "BAC",
        "WFC",
        "GS",
        "MS",
        "AXP",
        "BLK",
        "SCHW",
        "V",
        "MA"
    ],
    "Healthcare": [
        "JNJ",
        "UNH",
        "LLY",
        "PFE",
        "ABBV",
        "MRK",
        "TMO",
        "ABT",
        "AMGN"
    ],
    "Consumer": [
        "WMT",
        "COST",
        "PG",
        "KO",
        "PEP",
        "MCD",
        "NKE",
        "HD",
        "SBUX",
        "TGT"
    ],
    "Industrials & Energy": [
        "CAT",
        "BA",
        "GE",
        "HON",
        "UPS",
        "LMT",
        "XOM",
        "CVX",
        "COP"
    ],
    "Comms & Utilities": [
        "DIS",
        "NFLX",
        "T",
        "VZ",
        "NEE",
        "DUK"
    ]
}

UNIVERSE = [t for names in SECTORS.values() for t in names]

START, END = "2019-01-01", "2025-01-01"


def write(name: str, payload: object) -> None:
    path = OUT / name
    path.write_text(json.dumps(payload, separators=(",", ":"), default=str) + "\n")
    print(f"  {name:<26} {path.stat().st_size / 1024:6.1f} KB")


# --------------------------------------------------------------------------- #
# Prices and the factor backtest
# --------------------------------------------------------------------------- #


def generate_factor_data() -> None:
    import yfinance as yf

    from factor_sim import get_factors, performance_metrics, run_backtest

    raw = yf.download(UNIVERSE, start=START, end=END, progress=False, auto_adjust=True)
    closes = raw["Close"]
    # Drop any name without a full history rather than forward-filling one:
    # a synthetic price would flow straight into the factor scores.
    complete = [t for t in UNIVERSE if t in closes.columns and closes[t].notna().all()]
    closes = closes[complete].dropna(how="any")
    print(f"    universe: {len(complete)}/{len(UNIVERSE)} with a complete history")

    # Round *before* backtesting, not just before serialising. The browser
    # receives cents-rounded prices, so the golden fixture has to be computed
    # on exactly those numbers -- otherwise the port is measured against a
    # result it never had the inputs to reproduce.
    closes = closes.round(2)

    write(
        "factor-prices.json",
        {
            "start": START,
            "end": END,
            "source": "Yahoo Finance daily adjusted closes",
            "dates": [d.date().isoformat() for d in closes.index],
            # Cents precision: the backtest is ratio-based, so more digits
            # only inflate the payload.
            "tickers": list(closes.columns),
            "sectors": {
                name: [t for t in members if t in closes.columns]
                for name, members in SECTORS.items()
            },
            "closes": {t: [float(v) for v in closes[t]] for t in closes.columns},
        },
    )

    # Golden fixtures: the TypeScript port must reproduce these.
    # The fixtures pin a fixed slice and a fixed ticker set, so regenerating
    # with a wider universe does not silently invalidate them.
    golden_tickers = ["AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "AVGO", "ORCL"]
    golden_frame = closes[golden_tickers].loc["2021-01-01":"2025-01-01"]

    cases = []
    for names in (["momentum"], ["low_volatility"], ["momentum", "low_volatility"]):
        for top_n in (2, 3):
            result = run_backtest(
                golden_frame, get_factors(names), top_n=top_n, rebalance_every=21
            )
            metrics = performance_metrics(result.nav)
            cases.append(
                {
                    "factors": names,
                    "top_n": top_n,
                    "rebalance_every": 21,
                    "final_nav": round(result.final_nav, 4),
                    "total_return": round(metrics["total_return"], 6),
                    "sharpe_ratio": round(metrics["sharpe_ratio"], 6),
                    "max_drawdown": round(metrics["max_drawdown"], 6),
                    "rebalances": len(result.rebalance_dates),
                    # Sampled so the fixture stays small but still pins the path.
                    "nav_samples": [
                        round(float(v), 4) for v in result.nav["NAV"][::50]
                    ],
                }
            )
    write(
        "factor-golden.json",
        {
            "initial_cash": 100000.0,
            "tickers": golden_tickers,
            "start": "2021-01-01",
            "end": "2025-01-01",
            "cases": cases,
        },
    )


# --------------------------------------------------------------------------- #
# Earnings drift
# --------------------------------------------------------------------------- #


def generate_earnings_data() -> None:
    import pandas as pd
    import yfinance as yf

    from earnings_drift import EarningsReport, Stock, analyze_drift
    from earnings_drift.drift import surprise_correlation

    series = []
    for ticker in UNIVERSE:
        handle = yf.Ticker(ticker)
        table = handle.get_earnings_dates(limit=40)
        table = table.dropna(subset=["EPS Estimate", "Reported EPS"])
        # Announcements only; future scheduled dates have no reported EPS.
        table = table[table.index.date <= date.today()]
        if table.empty:
            continue

        prices = yf.download(
            ticker, start="2017-01-01", end=END, progress=False, auto_adjust=True
        )
        if prices is None or prices.empty:
            continue
        if isinstance(prices.columns, pd.MultiIndex):
            prices.columns = prices.columns.get_level_values(0)

        stock = Stock(ticker)
        stock.set_price_data(prices)
        for stamp, row in table.iterrows():
            stock.add_earnings(
                EarningsReport(
                    event_date=stamp.date(),
                    eps_actual=float(row["Reported EPS"]),
                    eps_estimate=float(row["EPS Estimate"]),
                )
            )

        drift = analyze_drift(stock, horizons=(1, 5, 10))
        if drift.empty:
            continue
        print(f"    {ticker}: {len(drift)} events")

        series.append(
            {
                "ticker": ticker,
                "correlation_1d": surprise_correlation(drift, 1),
                "correlation_5d": surprise_correlation(drift, 5),
                "events": [
                    {
                        "date": r["event_date"].isoformat(),
                        "surprise": round(float(r["surprise_pct"]), 3),
                        "d1": round(float(r["1d"]), 5),
                        "d5": round(float(r["5d"]), 5),
                        "d10": round(float(r["10d"]), 5),
                    }
                    for _, r in drift.iterrows()
                    if pd.notna(r["surprise_pct"])
                    and all(pd.notna(r[c]) for c in ("1d", "5d", "10d"))
                ],
            }
        )

    write(
        "earnings-drift.json",
        {
            "source": "Yahoo Finance: reported vs estimated EPS, daily adjusted closes",
            "computed_by": "earnings_drift.analyze_drift",
            "series": series,
        },
    )


# --------------------------------------------------------------------------- #
# Course catalogue
# --------------------------------------------------------------------------- #


def generate_catalog_data() -> None:
    from course_catalog import Catalog

    catalog = Catalog.bundled()
    write(
        "courses.json",
        {
            "courses": [
                {
                    "code": c.code,
                    "name": c.name,
                    "instructor": c.instructor,
                    "location": c.location,
                    "meetings": [
                        {"day": int(m.day), "start": m.start, "end": m.end}
                        for m in c.meetings
                    ],
                }
                for c in catalog
            ]
        },
    )

    # Every pair, with the Python's conflict verdict.
    courses = list(catalog)
    pairs = [
        {"a": a.code, "b": b.code, "conflicts": a.conflicts_with(b)}
        for i, a in enumerate(courses)
        for b in courses[i + 1 :]
    ]
    write("courses-golden.json", {"pairs": pairs})


# --------------------------------------------------------------------------- #
# Card scoring and trie search
# --------------------------------------------------------------------------- #


def generate_card_golden() -> None:
    import random

    from card_game import Card, Suit, score_cards
    from card_game.hand import HAND_SCORES

    rng = random.Random(11)
    deck = [Card(s, r) for s in Suit for r in ("2","3","4","5","6","7","8","9","10","J","Q","K","A")]

    cases = []
    for _ in range(400):
        hand = rng.sample(deck, 7)
        rank = score_cards(hand)
        cases.append(
            {
                "hand": [{"suit": c.suit.value, "rank": c.rank} for c in hand],
                "rank": rank.value,
                "points": HAND_SCORES[rank],
            }
        )
    write("cards-golden.json", {"cases": cases})


def generate_trie_golden() -> None:
    from trie_search import Trie

    words = sorted(
        {
            "park", "parks", "parking", "partner", "participate", "part", "party",
            "cat", "cot", "cut", "cart", "car", "care", "cargo", "carpet",
            "dog", "dodge", "door", "dot", "double", "down",
            "tree", "trees", "trie", "tried", "tries", "trip", "triple",
            "search", "searching", "season", "seat", "second", "sector",
            "index", "indexed", "indices", "inform", "input", "insert",
        }
    )
    trie: Trie = Trie({w: {f"https://example.com/{w}"} for w in words})

    queries = ["par", "ca", "tri", "se", "in", "z", ""]
    wildcards = ["c?t", "par?", "?og", "tr?e", "??", "c??t", "z?z"]

    write(
        "trie-golden.json",
        {
            "words": words,
            "prefix": {q: sorted(trie.keys_with_prefix(q)) for q in queries},
            "wildcard": {q: sorted(k for k, _ in trie.wildcard_search(q)) for q in wildcards},
        },
    )


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    print("generating demo data:")
    generate_catalog_data()
    generate_card_golden()
    generate_trie_golden()
    generate_factor_data()
    generate_earnings_data()
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
