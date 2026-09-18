"""The four filing-research tools, and the wiring that registers them."""

from __future__ import annotations

from ..cache import CacheBackend
from ..contracts import (
    Capability,
    CompanyFactsArgs,
    FetchSectionArgs,
    PriceReactionArgs,
    SearchFilingsArgs,
)
from ..data import EdgarClient, PriceClient
from ..telemetry import TelemetryRecorder
from .registry import Tool, ToolRegistry


def build_registry(
    edgar: EdgarClient,
    prices: PriceClient,
    cache: CacheBackend,
    telemetry: TelemetryRecorder,
    default_ttl: int = 3600,
) -> ToolRegistry:
    registry = ToolRegistry(cache=cache, telemetry=telemetry, default_ttl=default_ttl)

    async def search_filings(args: SearchFilingsArgs):
        return await edgar.search_filings(
            ticker=args.ticker, form_type=args.form_type.value, limit=args.limit
        )

    async def fetch_filing_section(args: FetchSectionArgs):
        return await edgar.fetch_section(
            ticker=args.ticker,
            accession=args.accession,
            section=args.section,
            max_chars=args.max_chars,
        )

    async def company_financials(args: CompanyFactsArgs):
        return await edgar.company_facts(
            ticker=args.ticker, concept=args.concept, periods=args.periods
        )

    async def price_reaction(args: PriceReactionArgs):
        return await prices.event_reaction(
            ticker=args.ticker, event_date=args.event_date, horizons=args.horizons
        )

    registry.register(
        Tool(
            name="search_filings",
            description=(
                "List a company's recent SEC filings of a given form type. Returns "
                "accession numbers, filing dates, and period-of-report dates. Use this "
                "first to find the accession number that the other tools need."
            ),
            args_model=SearchFilingsArgs,
            capability=Capability.READ_FILINGS,
            handler=search_filings,
            # Filing lists change only when a company files; a day is safe.
            cache_ttl_seconds=86_400,
        )
    )
    registry.register(
        Tool(
            name="fetch_filing_section",
            description=(
                "Fetch the text of one section of a filing (business, risk_factors, "
                "mda, or financial_statements) given its accession number. Text is "
                "truncated to max_chars; check the `truncated` flag."
            ),
            args_model=FetchSectionArgs,
            capability=Capability.READ_FILINGS,
            handler=fetch_filing_section,
            # Filing text is immutable once filed.
            cache_ttl_seconds=604_800,
        )
    )
    registry.register(
        Tool(
            name="company_financials",
            description=(
                "Fetch reported XBRL values for a US-GAAP concept (e.g. Revenues, "
                "NetIncomeLoss, OperatingIncomeLoss, Assets) across recent periods, "
                "newest first. Use for quantitative claims instead of reading tables."
            ),
            args_model=CompanyFactsArgs,
            capability=Capability.READ_FINANCIALS,
            handler=company_financials,
            cache_ttl_seconds=86_400,
        )
    )
    registry.register(
        Tool(
            name="price_reaction",
            description=(
                "Cumulative stock return over N trading days following an event date, "
                "measured from the last close on or before that date. Use to quantify "
                "how the market reacted to a filing."
            ),
            args_model=PriceReactionArgs,
            capability=Capability.READ_PRICES,
            handler=price_reaction,
            cache_ttl_seconds=86_400,
        )
    )
    return registry
