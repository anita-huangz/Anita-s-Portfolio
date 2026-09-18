"""Daily close prices and event-window returns.

Sourced from Yahoo Finance's public chart endpoint -- no key, no account. The
only computation here is a cumulative return over N *trading* days, measured
from the close on (or immediately before) the event date.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import httpx

from ..config import Settings
from ..contracts import PriceReaction
from ..errors import UpstreamDataError

CHART_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"


class PriceClient:
    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=settings.http_timeout_seconds,
            headers={"User-Agent": settings.sec_user_agent},
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def daily_closes(
        self, ticker: str, start: date, end: date
    ) -> list[tuple[date, float]]:
        """Ascending (date, close) pairs over an inclusive range."""
        params = {
            "period1": str(int(datetime.combine(start, datetime.min.time(), UTC).timestamp())),
            "period2": str(int(datetime.combine(end, datetime.min.time(), UTC).timestamp())),
            "interval": "1d",
        }
        url = CHART_URL.format(ticker=ticker.upper())
        try:
            response = await self._client.get(url, params=params)
        except httpx.HTTPError as exc:
            raise UpstreamDataError(f"price request failed for {ticker}: {exc}") from exc
        if response.status_code >= 400:
            raise UpstreamDataError(
                f"price source returned {response.status_code} for {ticker}"
            )

        payload = response.json()
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            error = (payload.get("chart") or {}).get("error")
            raise UpstreamDataError(f"no price data for {ticker}: {error}")

        block = result[0]
        stamps = block.get("timestamp") or []
        quote = (block.get("indicators", {}).get("quote") or [{}])[0]
        closes = quote.get("close") or []

        series: list[tuple[date, float]] = []
        for ts, close in zip(stamps, closes, strict=False):
            if close is None:
                continue  # Yahoo emits nulls for halted sessions.
            series.append(
                (datetime.fromtimestamp(ts, tz=UTC).date(), float(close))
            )
        series.sort(key=lambda row: row[0])
        return series

    async def event_reaction(
        self, ticker: str, event_date: date, horizons: list[int]
    ) -> PriceReaction:
        """Cumulative return over each horizon, measured in trading days."""
        longest = max(horizons)
        # Pad generously on both sides: weekends, holidays, and the possibility
        # that the event date itself was not a trading session.
        series = await self.daily_closes(
            ticker,
            event_date - timedelta(days=10),
            event_date + timedelta(days=longest * 2 + 15),
        )
        if not series:
            raise UpstreamDataError(f"no price history around {event_date} for {ticker}")

        baseline_idx = _baseline_index(series, event_date)
        if baseline_idx is None:
            raise UpstreamDataError(
                f"no trading session on or before {event_date} for {ticker}"
            )
        baseline_close = series[baseline_idx][1]

        windows: dict[str, float] = {}
        for horizon in horizons:
            target = baseline_idx + horizon
            if target >= len(series):
                continue  # Not enough history yet; omit rather than guess.
            windows[f"{horizon}d"] = (series[target][1] / baseline_close) - 1.0

        return PriceReaction(
            ticker=ticker.upper(),
            event_date=event_date,
            baseline_close=baseline_close,
            windows=windows,
        )


def _baseline_index(series: list[tuple[date, float]], event_date: date) -> int | None:
    """Index of the last session on or before the event date."""
    candidate: int | None = None
    for i, (day, _) in enumerate(series):
        if day <= event_date:
            candidate = i
        else:
            break
    return candidate
