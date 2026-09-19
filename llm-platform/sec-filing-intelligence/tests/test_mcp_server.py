"""The MCP server surface, exercised against the fake data clients.

It was the only module here with no coverage at all — 40 statements wiring
every tool the platform exposes to external MCP clients. A break in it would
not fail any other test, because nothing else imports it.

These use the same fake EDGAR and price clients as the rest of the suite, so
nothing reaches the network, and they route through the real registry so the
capability checks and typed failures are the real ones.
"""

import pytest

from filing_intel import mcp_server
from filing_intel.contracts import Capability


@pytest.fixture
def wired(monkeypatch, registry, edgar, prices, cache, telemetry):
    """Point the module's runtime singleton at the test doubles."""

    class Runtime:
        """The slice of FilingIntelRuntime the MCP surface actually uses."""

        def __init__(self):
            self.registry = registry
            self.telemetry = telemetry

        def telemetry_summary(self):
            return self.telemetry.summarize()

    runtime = Runtime()
    monkeypatch.setattr(mcp_server, "_runtime", runtime)
    return runtime


class TestRuntimeSingleton:
    def test_it_is_built_once_and_reused(self, monkeypatch):
        built = []

        class Fake:
            @staticmethod
            def build():
                built.append(1)
                return Fake()

        monkeypatch.setattr(mcp_server, "_runtime", None)
        monkeypatch.setattr(mcp_server, "FilingIntelRuntime", Fake)
        first = mcp_server.runtime()
        second = mcp_server.runtime()
        assert first is second
        assert len(built) == 1, "the runtime must not be rebuilt per call"


class TestServerDeclaration:
    def test_the_server_is_named_and_versioned(self):
        assert mcp_server.server.name == "sec-filing-intelligence"
        assert mcp_server.server.version

    def test_the_instructions_tell_a_client_the_call_order(self):
        text = mcp_server.server.instructions.lower()
        assert "search_filings" in text, "a client needs to know what to call first"

    def test_main_is_exposed_as_the_entry_point(self):
        assert callable(mcp_server.main)


class TestRouting:
    @pytest.mark.asyncio
    async def test_a_call_goes_through_the_registry(self, wired):
        data = await mcp_server._call("search_filings", {"ticker": "AAPL"})
        assert data

    @pytest.mark.asyncio
    async def test_a_failure_becomes_an_exception_the_client_can_see(self, wired):
        """MCP has no typed-failure channel, so a failed result must raise."""
        with pytest.raises(ValueError) as error:
            await mcp_server._call("definitely_not_a_tool", {})
        assert str(error.value), "the message must name the failure kind"

    @pytest.mark.asyncio
    async def test_every_capability_is_granted_to_an_mcp_caller(self, wired):
        """Each tool here is a public-data read; a missing capability would
        make the tool unreachable rather than merely restricted."""
        recorded = {}
        real = wired.registry.execute

        async def spy(name, arguments, capabilities=None, trace_id=None):
            recorded["capabilities"] = capabilities
            return await real(name, arguments, capabilities=capabilities,
                              trace_id=trace_id)

        wired.registry.execute = spy
        await mcp_server._call("search_filings", {"ticker": "AAPL"})
        assert set(recorded["capabilities"]) == set(Capability)

    @pytest.mark.asyncio
    async def test_the_trace_id_marks_the_call_as_coming_from_mcp(self, wired):
        recorded = {}
        real = wired.registry.execute

        async def spy(name, arguments, capabilities=None, trace_id=None):
            recorded["trace_id"] = trace_id
            return await real(name, arguments, capabilities=capabilities,
                              trace_id=trace_id)

        wired.registry.execute = spy
        await mcp_server._call("search_filings", {"ticker": "AAPL"})
        assert recorded["trace_id"].startswith("mcp-")


class TestTools:
    @pytest.mark.asyncio
    async def test_search_filings_returns_accessions(self, wired):
        result = await mcp_server.search_filings(ticker="AAPL")
        assert result

    @pytest.mark.asyncio
    async def test_telemetry_summary_is_callable(self, wired):
        assert await mcp_server.telemetry_summary() is not None

    @pytest.mark.asyncio
    async def test_an_unknown_ticker_raises_rather_than_returning_nothing(self, wired):
        with pytest.raises(ValueError):
            await mcp_server.search_filings(ticker="NOT-A-REAL-TICKER")
