"""Network-facing loaders. Imported lazily so the core runs without them."""

from __future__ import annotations

import numpy as np
import pandas as pd


def download_prices(tickers: list[str], start: str, end: str) -> pd.DataFrame:
    """Daily adjusted closes, one column per ticker."""
    import yfinance as yf

    raw = yf.download(
        tickers, start=start, end=end, progress=False, auto_adjust=True
    )
    if raw is None or raw.empty:
        raise ValueError(f"no price data for {tickers} between {start} and {end}")

    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    if isinstance(closes, pd.Series):
        closes = closes.to_frame(tickers[0])
    return closes.sort_index().dropna(how="all")


def fetch_fundamentals(tickers: list[str]) -> pd.DataFrame:
    """Current P/E and market cap.

    These are a *present-day* snapshot. Applying them to a historical rebalance
    is look-ahead bias; `cli.py` warns when value or size factors are requested.
    Only price-derived factors are genuinely point-in-time here.
    """
    from yahooquery import Ticker

    query = Ticker(tickers)
    detail = query.summary_detail
    rows = {}
    for ticker in tickers:
        summary = detail.get(ticker) if isinstance(detail, dict) else None
        if not isinstance(summary, dict):
            summary = {}
        rows[ticker] = {
            "PE": summary.get("trailingPE", np.nan),
            "MarketCap": summary.get("marketCap", np.nan),
        }
    return pd.DataFrame.from_dict(rows, orient="index")


def load_fama_french() -> pd.DataFrame:
    """Daily Fama-French research factors, converted from percent to decimal."""
    import pandas_datareader.data as web

    frame = web.DataReader("F-F_Research_Data_Factors_daily", "famafrench")[0]
    frame.index = pd.to_datetime(frame.index)
    frame = frame.rename(columns=lambda c: c.strip())
    return frame / 100.0
