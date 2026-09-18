"""MCP server.

Exposes the same tools the internal agent uses, so an external MCP client
(Claude Code, Claude Desktop, any other host) reaches the identical capability
surface -- same Pydantic validation, same cache, same telemetry -- rather than a
parallel implementation that drifts.

`research_filings` additionally exposes the whole multi-agent workflow as a
single tool, for hosts that want the answer rather than the raw evidence.

Run with:  filing-intel-mcp        (stdio transport)
"""

from __future__ import annotations

from datetime import date
from typing import Any

from mcp.server.mcpserver import MCPServer

from .contracts import (
    Capability,
    FilingSection,
    FormType,
    ResearchRequest,
)
from .runtime import FilingIntelRuntime

server: MCPServer = MCPServer(
    name="sec-filing-intelligence",
    version="0.1.0",
    instructions=(
        "Research US public-company SEC filings. Call search_filings first to "
        "obtain an accession number, then fetch_filing_section or "
        "company_financials. Use research_filings to delegate a whole question."
    ),
)

_runtime: FilingIntelRuntime | None = None


def runtime() -> FilingIntelRuntime:
    global _runtime
    if _runtime is None:
        _runtime = FilingIntelRuntime.build()
    return _runtime


async def _call(name: str, arguments: dict[str, Any]) -> Any:
    """Route through the registry so MCP callers get the same enforcement."""
    result = await runtime().registry.execute(
        name,
        arguments,
        # An MCP client is a read-only research caller: every capability here is
        # a public-data read, and nothing in the set can mutate state.
        capabilities=list(Capability),
        trace_id=f"mcp-{name}",
    )
    if not result.ok:
        raise ValueError(f"{result.error_kind}: {result.error}")
    return result.data


@server.tool(
    description=(
        "List a company's recent SEC filings of a given form type. Returns "
        "accession numbers and filing dates needed by the other tools."
    )
)
async def search_filings(
    ticker: str, form_type: FormType = FormType.ANNUAL, limit: int = 5
) -> list[dict[str, Any]]:
    return await _call(
        "search_filings",
        {"ticker": ticker, "form_type": form_type.value, "limit": limit},
    )


@server.tool(
    description=(
        "Fetch one section of a filing by accession number. Sections: business, "
        "risk_factors, mda, financial_statements."
    )
)
async def fetch_filing_section(
    ticker: str,
    accession: str,
    section: FilingSection = FilingSection.RISK_FACTORS,
    max_chars: int = 20000,
) -> dict[str, Any]:
    return await _call(
        "fetch_filing_section",
        {
            "ticker": ticker,
            "accession": accession,
            "section": section.value,
            "max_chars": max_chars,
        },
    )


@server.tool(
    description=(
        "Reported XBRL values for a US-GAAP concept (Revenues, NetIncomeLoss, "
        "Assets, ...) across recent periods, newest first."
    )
)
async def company_financials(
    ticker: str, concept: str = "Revenues", periods: int = 8
) -> list[dict[str, Any]]:
    return await _call(
        "company_financials", {"ticker": ticker, "concept": concept, "periods": periods}
    )


@server.tool(
    description=(
        "Cumulative stock return over N trading days after an event date, "
        "measured from the last close on or before it."
    )
)
async def price_reaction(
    ticker: str, event_date: date, horizons: list[int] | None = None
) -> dict[str, Any]:
    return await _call(
        "price_reaction",
        {
            "ticker": ticker,
            "event_date": event_date.isoformat(),
            "horizons": horizons or [1, 5, 10],
        },
    )


@server.tool(
    description=(
        "Run the full multi-agent research workflow against a question about a "
        "company's filings. Returns a cited answer plus token and cost accounting. "
        "Slower and more expensive than the individual tools -- use it when you "
        "want a researched conclusion rather than raw evidence."
    )
)
async def research_filings(ticker: str, question: str) -> dict[str, Any]:
    response = await runtime().research(
        ResearchRequest(ticker=ticker, question=question)
    )
    return response.model_dump(mode="json")


@server.tool(
    description=(
        "Aggregate telemetry for this server process: model calls, tool calls, "
        "token usage, estimated spend, failure rates, and latency percentiles."
    )
)
async def telemetry_summary() -> dict[str, Any]:
    return runtime().telemetry_summary().model_dump(mode="json")


def main() -> None:
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
