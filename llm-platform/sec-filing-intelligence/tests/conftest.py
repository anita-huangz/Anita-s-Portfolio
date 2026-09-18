"""Shared fixtures.

The fakes here stand in for the two network sources (EDGAR, prices) and for the
model. Everything else -- registry, cache, telemetry, graph, API -- is the real
implementation, so the tests exercise production code paths rather than mocks of
themselves.
"""

from __future__ import annotations

from datetime import date

import pytest

from filing_intel.cache import InMemoryCache, SessionStore
from filing_intel.config import Settings
from filing_intel.contracts import (
    Filing,
    FilingSection,
    FinancialFact,
    ModelResponse,
    PriceReaction,
    SectionText,
    TokenUsage,
    ToolCall,
)
from filing_intel.errors import UpstreamDataError
from filing_intel.telemetry import TelemetryRecorder
from filing_intel.tools import build_registry

APPL_FILING = Filing(
    accession="0000320193-23-000106",
    ticker="AAPL",
    cik="0000320193",
    form_type="10-K",
    filed_at=date(2023, 11, 3),
    period_of_report=date(2023, 9, 30),
    primary_document="aapl-20230930.htm",
)


class FakeEdgar:
    """In-memory EDGAR. Records calls so tests can assert on access patterns."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple]] = []
        self.fail_with: Exception | None = None

    async def aclose(self) -> None:
        return None

    async def cik_for(self, ticker: str) -> str:
        if ticker.upper() != "AAPL":
            raise UpstreamDataError(f"no SEC registrant found for ticker {ticker!r}")
        return "0000320193"

    async def search_filings(self, ticker: str, form_type: str = "10-K", limit: int = 5):
        self.calls.append(("search_filings", (ticker, form_type, limit)))
        if self.fail_with:
            raise self.fail_with
        await self.cik_for(ticker)
        return [APPL_FILING][:limit]

    async def fetch_section(
        self, ticker: str, accession: str, section: FilingSection, max_chars: int = 20000
    ):
        self.calls.append(("fetch_section", (ticker, accession, section, max_chars)))
        if self.fail_with:
            raise self.fail_with
        body = (
            "The Company's business could be materially adversely affected by "
            "supply chain concentration in a small number of manufacturing partners."
        )
        return SectionText(
            accession=accession,
            section=section,
            text=body[:max_chars],
            char_count=len(body),
            truncated=len(body) > max_chars,
        )

    async def company_facts(self, ticker: str, concept: str = "Revenues", periods: int = 8):
        self.calls.append(("company_facts", (ticker, concept, periods)))
        if self.fail_with:
            raise self.fail_with
        return [
            FinancialFact(
                concept=concept,
                unit="USD",
                value=383_285_000_000.0,
                period_end=date(2023, 9, 30),
                fiscal_year=2023,
                fiscal_period="FY",
                form_type="10-K",
            )
        ][:periods]


class FakePrices:
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    async def aclose(self) -> None:
        return None

    async def event_reaction(self, ticker: str, event_date: date, horizons: list[int]):
        self.calls.append((ticker, event_date, tuple(horizons)))
        return PriceReaction(
            ticker=ticker,
            event_date=event_date,
            baseline_close=170.0,
            windows={f"{h}d": 0.01 * h for h in horizons},
        )


@pytest.fixture
def settings() -> Settings:
    return Settings(
        provider="replay",
        model="claude-opus-5",
        redis_url=None,
        sec_user_agent="filing-intel-tests/0.1 (tests@example.com)",
        agent_max_tool_calls=4,
    )


@pytest.fixture
def cache() -> InMemoryCache:
    return InMemoryCache()


@pytest.fixture
def telemetry() -> TelemetryRecorder:
    return TelemetryRecorder()


@pytest.fixture
def edgar() -> FakeEdgar:
    return FakeEdgar()


@pytest.fixture
def prices() -> FakePrices:
    return FakePrices()


@pytest.fixture
def registry(edgar, prices, cache, telemetry):
    return build_registry(edgar, prices, cache, telemetry)


@pytest.fixture
def sessions(cache):
    return SessionStore(cache, ttl_seconds=60)


def text_response(text: str, **kwargs) -> ModelResponse:
    return ModelResponse(
        text=text,
        usage=kwargs.pop("usage", TokenUsage(input_tokens=100, output_tokens=50)),
        model=kwargs.pop("model", "claude-opus-5"),
        provider=kwargs.pop("provider", "scripted"),
        stop_reason=kwargs.pop("stop_reason", "end_turn"),
        **kwargs,
    )


def tool_response(name: str, arguments: dict, call_id: str = "tu_1") -> ModelResponse:
    return ModelResponse(
        text="",
        tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
        stop_reason="tool_use",
        usage=TokenUsage(input_tokens=200, output_tokens=80),
        model="claude-opus-5",
        provider="scripted",
        raw_content=[
            {"type": "tool_use", "id": call_id, "name": name, "input": arguments}
        ],
    )
