"""Assembly point.

Builds the object graph once -- provider, cache, sessions, tools, telemetry,
agent graph -- and exposes the single operation the platform offers. The FastAPI
app and the MCP server are both thin shells over this.
"""

from __future__ import annotations

import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from .agents import ResearchGraph
from .cache import CacheBackend, Session, SessionStore, build_cache
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

        response = self._finalize(request, session, state, trace_id, started)
        await self.sessions.save(session)
        return response

    async def research_stream(
        self, request: ResearchRequest
    ) -> AsyncIterator[dict[str, Any]]:
        """Emit a progress event per completed graph node, then a final result.

        The events mirror what `research` computes; this exists so a client can
        render the plan and the tool calls while the workflow is still running
        rather than staring at a spinner for the whole run.
        """
        started = time.perf_counter()
        trace_id = uuid.uuid4().hex
        session = await self.sessions.get_or_create(request.session_id, request.ticker)

        state: dict[str, Any] = {
            "ticker": request.ticker,
            "question": request.question,
            "trace_id": trace_id,
            "session_id": session.session_id,
            "capabilities": request.capabilities,
            "usage": TokenUsage(),
            "estimated_cost_usd": 0.0,
            "failures": [],
        }

        yield {
            "event": "started",
            "data": {
                "trace_id": trace_id,
                "session_id": session.session_id,
                "ticker": request.ticker,
            },
        }

        final: dict[str, Any] = {}
        reported_tools = 0
        try:
            async for node, node_state in self.graph.stream(state):
                final = {**final, **node_state}

                if node == "plan" and node_state.get("plan"):
                    yield {"event": "plan", "data": {"plan": node_state["plan"]}}

                if node == "tools":
                    evidence = [
                        e
                        for e in node_state.get("evidence", [])
                        if e.get("kind") == "tool_result"
                    ]
                    for item in evidence[reported_tools:]:
                        yield {
                            "event": "tool_call",
                            "data": {
                                "tool": item.get("tool"),
                                "ok": item.get("ok"),
                                "arguments": item.get("arguments"),
                                "error": None if item.get("ok") else item.get("data"),
                            },
                        }
                    reported_tools = len(evidence)

                if node == "analyze":
                    yield {
                        "event": "analysis",
                        "data": {
                            "answer": node_state.get("answer", ""),
                            "findings": [
                                f.model_dump(mode="json")
                                for f in node_state.get("findings", [])
                            ],
                        },
                    }
        except Exception as exc:
            yield {"event": "error", "data": {"message": f"{type(exc).__name__}: {exc}"}}
            return

        response = self._finalize(request, session, final, trace_id, started)
        await self.sessions.save(session)
        yield {"event": "result", "data": response.model_dump(mode="json")}

    def _finalize(
        self,
        request: ResearchRequest,
        session: Session,
        state: dict[str, Any],
        trace_id: str,
        started: float,
    ) -> ResearchResponse:
        """Fold a finished graph state into the response and the session."""
        usage = state.get("usage", TokenUsage())
        cost = state.get("estimated_cost_usd", 0.0)

        session.turns += 1
        session.usage = session.usage + usage
        session.estimated_cost_usd += cost
        session.ticker = request.ticker

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
