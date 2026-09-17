"""The typed boundary should reject bad input at the edge, not deep in a handler."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from filing_intel.contracts import (
    Filing,
    FormType,
    PriceReactionArgs,
    ResearchRequest,
    SearchFilingsArgs,
    TokenUsage,
    ToolResult,
)


def test_ticker_is_normalized_to_uppercase():
    assert SearchFilingsArgs(ticker=" aapl ").ticker == "AAPL"


@pytest.mark.parametrize("bad", ["", "TOOOOOOLONGTICKER", "123", "A B"])
def test_implausible_tickers_rejected(bad):
    with pytest.raises(ValidationError):
        SearchFilingsArgs(ticker=bad)


def test_unknown_fields_are_an_error():
    # extra="forbid" is what stops a typo'd tool argument from being silently
    # dropped and the handler quietly using a default.
    with pytest.raises(ValidationError):
        SearchFilingsArgs(ticker="AAPL", limmit=5)


def test_limit_bounds_enforced():
    with pytest.raises(ValidationError):
        SearchFilingsArgs(ticker="AAPL", limit=100)


def test_horizons_deduplicated_and_sorted():
    assert PriceReactionArgs(
        ticker="AAPL", event_date=date(2023, 11, 3), horizons=[10, 1, 5, 1]
    ).horizons == [1, 5, 10]


def test_horizons_must_be_non_empty():
    with pytest.raises(ValidationError):
        PriceReactionArgs(ticker="AAPL", event_date=date(2023, 11, 3), horizons=[])


def test_token_usage_adds_every_component():
    a = TokenUsage(input_tokens=1, output_tokens=2, cache_read_input_tokens=3)
    b = TokenUsage(input_tokens=10, output_tokens=20, cache_creation_input_tokens=5)
    total = a + b
    assert (total.input_tokens, total.output_tokens) == (11, 22)
    assert total.cache_read_input_tokens == 3
    assert total.cache_creation_input_tokens == 5
    assert total.total == 41


def test_filing_url_strips_dashes_and_leading_zeros():
    filing = Filing(
        accession="0000320193-23-000106",
        ticker="AAPL",
        cik="0000320193",
        form_type=FormType.ANNUAL.value,
        filed_at=date(2023, 11, 3),
        primary_document="aapl-20230930.htm",
    )
    assert filing.url == (
        "https://www.sec.gov/Archives/edgar/data/320193/"
        "000032019323000106/aapl-20230930.htm"
    )


def test_tool_result_renders_errors_with_their_kind():
    result = ToolResult(tool="x", ok=False, error="boom", error_kind="upstream_data")
    assert result.for_model() == "ERROR[upstream_data]: boom"


def test_tool_result_renders_success_as_sorted_json():
    result = ToolResult(tool="x", ok=True, data={"b": 1, "a": 2})
    assert result.for_model() == '{"a": 2, "b": 1}'


def test_research_request_defaults_to_full_capability_grant():
    request = ResearchRequest(ticker="aapl", question="What are the risks?")
    assert request.ticker == "AAPL"
    assert len(request.capabilities) == 3
