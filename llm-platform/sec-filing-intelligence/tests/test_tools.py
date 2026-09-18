"""Registry behaviour: least privilege, validation, caching, failure isolation."""

from __future__ import annotations

from datetime import date

import pytest

from filing_intel.contracts import Capability
from filing_intel.errors import UpstreamDataError

ALL = list(Capability)


async def execute(registry, name, args, caps=None):
    return await registry.execute(
        name, args, capabilities=caps if caps is not None else ALL, trace_id="t1"
    )


async def test_happy_path_returns_data(registry, edgar):
    result = await execute(registry, "search_filings", {"ticker": "AAPL"})
    assert result.ok
    assert result.data[0]["accession"] == "0000320193-23-000106"
    assert edgar.calls == [("search_filings", ("AAPL", "10-K", 5))]


async def test_unknown_tool_is_a_typed_failure_not_an_exception(registry):
    result = await execute(registry, "definitely_not_a_tool", {})
    assert not result.ok
    assert result.error_kind == "unknown_tool"


async def test_capability_is_enforced_even_when_the_model_asks(registry):
    """Hiding a tool from the model is not the control; this is."""
    result = await execute(
        registry, "price_reaction",
        {"ticker": "AAPL", "event_date": "2023-11-03"},
        caps=[Capability.READ_FILINGS],
    )
    assert not result.ok
    assert result.error_kind == "tool_not_permitted"
    assert "read_prices" in result.error


async def test_ungranted_tools_are_not_advertised(registry):
    specs = registry.specs_for([Capability.READ_FILINGS])
    names = {s.name for s in specs}
    assert names == {"search_filings", "fetch_filing_section"}


async def test_all_advertised_schemas_are_strict(registry):
    for spec in registry.specs_for(ALL):
        assert spec.strict is True
        assert spec.input_schema["additionalProperties"] is False
        # Strict mode requires every property to be listed as required.
        assert set(spec.input_schema["required"]) == set(spec.input_schema["properties"])


async def test_enum_refs_are_inlined_into_the_schema(registry):
    schema = next(s for s in registry.specs_for(ALL) if s.name == "search_filings")
    assert "$defs" not in schema.input_schema
    assert schema.input_schema["properties"]["form_type"]["enum"] == [
        "10-K", "10-Q", "8-K", "DEF 14A"
    ]


async def test_invalid_arguments_are_rejected_before_the_handler(registry, edgar):
    result = await execute(registry, "search_filings", {"ticker": "!!!"})
    assert not result.ok
    assert result.error_kind == "tool_input_invalid"
    assert edgar.calls == []  # handler never ran


async def test_extra_argument_is_rejected(registry):
    result = await execute(registry, "search_filings", {"ticker": "AAPL", "bogus": 1})
    assert not result.ok
    assert result.error_kind == "tool_input_invalid"


async def test_second_identical_call_is_served_from_cache(registry, edgar):
    first = await execute(registry, "search_filings", {"ticker": "AAPL"})
    second = await execute(registry, "search_filings", {"ticker": "AAPL"})
    assert first.cached is False
    assert second.cached is True
    assert second.data == first.data
    assert len(edgar.calls) == 1  # upstream hit exactly once


async def test_different_arguments_miss_the_cache(registry, edgar):
    await execute(registry, "search_filings", {"ticker": "AAPL", "limit": 1})
    await execute(registry, "search_filings", {"ticker": "AAPL", "limit": 2})
    assert len(edgar.calls) == 2


async def test_upstream_error_becomes_a_typed_result(registry, edgar):
    edgar.fail_with = UpstreamDataError("EDGAR returned 503")
    result = await execute(registry, "search_filings", {"ticker": "AAPL"})
    assert not result.ok
    assert result.error_kind == "upstream_data"
    assert "503" in result.error


async def test_unexpected_handler_exception_is_contained(registry, edgar):
    edgar.fail_with = RuntimeError("kaboom")
    result = await execute(registry, "search_filings", {"ticker": "AAPL"})
    assert not result.ok
    assert result.error_kind == "unhandled"
    assert "RuntimeError" in result.error


async def test_failures_are_not_cached(registry, edgar):
    edgar.fail_with = UpstreamDataError("transient")
    assert not (await execute(registry, "search_filings", {"ticker": "AAPL"})).ok
    edgar.fail_with = None
    retry = await execute(registry, "search_filings", {"ticker": "AAPL"})
    assert retry.ok and retry.cached is False


async def test_unknown_ticker_surfaces_as_upstream_error(registry):
    result = await execute(registry, "search_filings", {"ticker": "ZZZZ"})
    assert not result.ok
    assert "no SEC registrant" in result.error


async def test_every_outcome_emits_exactly_one_telemetry_event(registry, telemetry):
    await execute(registry, "search_filings", {"ticker": "AAPL"})      # ok
    await execute(registry, "search_filings", {"ticker": "AAPL"})      # cached
    await execute(registry, "search_filings", {"ticker": "!!!"})       # invalid
    await execute(registry, "nope", {})                                 # unknown
    events = telemetry.events
    assert len(events) == 4
    assert [e.ok for e in events] == [True, True, False, False]
    assert [e.cached for e in events] == [False, True, False, False]


async def test_price_tool_roundtrip(registry, prices):
    result = await execute(
        registry, "price_reaction",
        {"ticker": "AAPL", "event_date": "2023-11-03", "horizons": [1, 5]},
    )
    assert result.ok
    assert result.data["windows"] == {"1d": 0.01, "5d": 0.05}
    assert prices.calls[0][1] == date(2023, 11, 3)


async def test_financials_tool_roundtrip(registry):
    result = await execute(registry, "company_financials", {"ticker": "AAPL"})
    assert result.ok
    assert result.data[0]["concept"] == "Revenues"
    assert result.data[0]["unit"] == "USD"


async def test_duplicate_registration_is_rejected(registry):
    from filing_intel.contracts import SearchFilingsArgs
    from filing_intel.tools import Tool

    async def noop(args):
        return None

    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            Tool(
                name="search_filings",
                description="dupe",
                args_model=SearchFilingsArgs,
                capability=Capability.READ_FILINGS,
                handler=noop,
            )
        )
