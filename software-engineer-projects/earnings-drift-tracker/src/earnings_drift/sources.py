"""Network-facing loaders.

Credentials come from the environment. The previous version called `input()` at
module scope, which meant importing the module prompted for a key -- so nothing
downstream could be imported, scripted, or tested.
"""

from __future__ import annotations

import os

import pandas as pd
import requests

from .models import EarningsReport

FMP_SURPRISES_URL = "https://financialmodelingprep.com/api/v3/earnings-surprises/{ticker}"


class MissingAPIKey(RuntimeError):
    pass


def fmp_api_key() -> str:
    key = os.environ.get("FMP_API_KEY", "").strip()
    if not key:
        raise MissingAPIKey(
            "set FMP_API_KEY (free tier: https://financialmodelingprep.com/developer/docs)"
        )
    return key


def load_price_data(ticker: str, start: str, end: str) -> pd.DataFrame:
    """Daily OHLCV from Yahoo Finance."""
    import yfinance as yf

    frame = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
    if frame is None or frame.empty:
        raise ValueError(f"no price data returned for {ticker} between {start} and {end}")
    # yfinance returns a column MultiIndex for multi-ticker requests and
    # sometimes for single-ticker ones too; flatten so 'Close' is reachable.
    if isinstance(frame.columns, pd.MultiIndex):
        frame.columns = frame.columns.get_level_values(0)
    return frame.sort_index()


def parse_surprises(payload: list[dict]) -> list[EarningsReport]:
    """Convert an FMP earnings-surprises payload into reports, skipping blanks."""
    reports: list[EarningsReport] = []
    for item in payload:
        actual = item.get("actualEarningResult")
        estimate = item.get("estimatedEarning")
        day = item.get("date")
        if actual is None or estimate is None or not day:
            continue
        try:
            reports.append(EarningsReport.from_iso(day, actual, estimate))
        except (TypeError, ValueError):
            continue
    return sorted(reports, key=lambda r: r.event_date)


def load_earnings(ticker: str, limit: int = 12, timeout: float = 20.0) -> list[EarningsReport]:
    response = requests.get(
        FMP_SURPRISES_URL.format(ticker=ticker),
        params={"limit": limit, "apikey": fmp_api_key()},
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError(f"unexpected FMP response for {ticker}: {payload!r}")
    return parse_surprises(payload)
