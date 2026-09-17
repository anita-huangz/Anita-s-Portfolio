"""Assembly point.

Builds the object graph once -- provider, cache, sessions, tools, telemetry,
agent graph -- and exposes the single operation the platform offers. The FastAPI
app and the MCP server are both thin shells over this.
"""

from __future__ import annotations

import time
import uuid

from .agents import ResearchGraph
from .cache import CacheBackend, SessionStore, build_cache
from .config import Settings, get_settings
from .contracts import ResearchRequest, ResearchResponse, TokenUsage
from .data import EdgarClient, PriceClient
from .providers.base import ModelProvider
from .providers.registry import build_provider
from .telemetry import TelemetryRecorder, TelemetrySummary
from .tools import ToolRegistry, build_registry


class FilingIntelRuntime:
    def __init__(
        self,
        settings: Settings,
        provider: ModelProvider,
        cache: CacheBackend,
        edgar: EdgarClient,
        prices: PriceClient,
        telemetry: TelemetryRecorder | None = None,
    ) -> None:
        self.settings = settings
        self.provider = provider
        self.cache = cache
        self.edgar = edgar
        self.prices = prices
        self.telemetry = telemetry or TelemetryRecorder()
        self.registry: ToolRegistry = build_registry(
            edgar, prices, cache, self.telemetry, settings.cache_ttl_seconds
        )
        self.sessions = SessionStore(cache, settings.session_ttl_seconds)
        self.graph = ResearchGraph(provider, self.registry, self.telemetry, settings)

    @classmethod
    def build(cls, settings: Settings | None = None) -> FilingIntelRuntime:
        settings = settings or get_settings()
        cache = build_cache(settings.redis_url)
        return cls(
            settings=settings,
            provider=build_provider(settings),
            cache=cache,
            edgar=EdgarClient(settings),
            prices=PriceClient(settings),
        )

    async def aclose(self) -> None:
        await self.edgar.aclose()
        await self.prices.aclose()

    async def research(self, request: ResearchRequest) -> ResearchResponse:
        started = time.perf_counter()
        trace_id = uuid.uuid4().hex
        session = await self.sessions.get_or_create(request.session_id, request.ticker)

        state = await self.graph.run(
            {
                "ticker": request.ticker,
                "question": request.question,
                "trace_id": trace_id,
                "session_id": session.session_id,
                "capabilities": request.capabilities,
                "usage": TokenUsage(),
                "estimated_cost_usd": 0.0,
                "failures": [],
            }
        )

        usage = state.get("usage", TokenUsage())
        cost = state.get("estimated_cost_usd", 0.0)

        session.turns += 1
        session.usage = session.usage + usage
        session.estimated_cost_usd += cost
        session.ticker = request.ticker
        await self.sessions.save(session)

        note = state.get("verifier_note")
        failures = state.get("failures") or []
        if failures:
            note = "; ".join(filter(None, [note, *failures]))

        return ResearchResponse(
            ticker=request.ticker,
            question=request.question,
            answer=state.get("answer", ""),
            findings=state.get("findings", []),
            session_id=session.session_id,
            trace_id=trace_id,
            tool_calls_made=state.get("tool_calls_made", 0),
            usage=usage,
            estimated_cost_usd=cost,
            latency_ms=(time.perf_counter() - started) * 1000,
            verified=state.get("verified", False),
            verifier_note=note,
        )

    def telemetry_summary(self) -> TelemetrySummary:
        return self.telemetry.summarize()
