"""Collects telemetry events and answers aggregate questions about them.

Deliberately in-process with a bounded buffer. The point of this module is the
*shape* of the aggregation -- spend and failure rate sliced by model, provider,
and tool -- not durable storage. `RedisTelemetrySink` mirrors events into a
capped Redis list so a multi-worker deployment can aggregate across processes.
"""

from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from collections.abc import Iterable
from typing import Any, Protocol

from pydantic import Field

from ..contracts import Strict, TokenUsage
from .events import ModelCallEvent, TelemetryEvent, ToolCallEvent


class TelemetrySink(Protocol):
    async def emit(self, event: TelemetryEvent) -> None: ...


class ModelSlice(Strict):
    calls: int = 0
    failures: int = 0
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost_usd: float = 0.0


class ToolSlice(Strict):
    calls: int = 0
    failures: int = 0
    cache_hits: int = 0
    p50_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0


class TelemetrySummary(Strict):
    total_model_calls: int = 0
    total_tool_calls: int = 0
    total_usage: TokenUsage = Field(default_factory=TokenUsage)
    total_estimated_cost_usd: float = 0.0
    model_failure_rate: float = 0.0
    tool_failure_rate: float = 0.0
    cache_hit_rate: float = 0.0
    p50_model_latency_ms: float = 0.0
    p95_model_latency_ms: float = 0.0
    by_model: dict[str, ModelSlice] = Field(default_factory=dict)
    by_tool: dict[str, ToolSlice] = Field(default_factory=dict)
    failures_by_kind: dict[str, int] = Field(default_factory=dict)


def percentile(values: list[float], pct: float) -> float:
    """Nearest-rank percentile. Returns 0.0 for an empty sample."""
    if not values:
        return 0.0
    ordered = sorted(values)
    # Nearest-rank: ceil(pct * n), clamped into range.
    rank = max(1, min(len(ordered), int(-(-pct * len(ordered) // 1))))
    return ordered[rank - 1]


class TelemetryRecorder:
    """Thread-safe-by-lock, bounded, in-process event buffer."""

    def __init__(self, max_events: int = 10_000, sink: TelemetrySink | None = None) -> None:
        self._events: list[TelemetryEvent] = []
        self._max_events = max_events
        self._sink = sink
        self._lock = asyncio.Lock()

    async def record(self, event: TelemetryEvent) -> None:
        async with self._lock:
            self._events.append(event)
            if len(self._events) > self._max_events:
                # Drop oldest. A portfolio-scale buffer, not a metrics backend.
                del self._events[: len(self._events) - self._max_events]
        if self._sink is not None:
            await self._sink.emit(event)

    @property
    def events(self) -> list[TelemetryEvent]:
        return list(self._events)

    def clear(self) -> None:
        self._events.clear()

    def summarize(self, events: Iterable[TelemetryEvent] | None = None) -> TelemetrySummary:
        evs = list(self._events if events is None else events)
        model_events = [e for e in evs if isinstance(e, ModelCallEvent)]
        tool_events = [e for e in evs if isinstance(e, ToolCallEvent)]

        by_model: dict[str, ModelSlice] = {}
        for e in model_events:
            slice_ = by_model.setdefault(e.model, ModelSlice())
            slice_.calls += 1
            slice_.failures += 0 if e.ok else 1
            slice_.usage = slice_.usage + e.usage
            slice_.estimated_cost_usd += e.estimated_cost_usd

        tool_latencies: dict[str, list[float]] = defaultdict(list)
        by_tool: dict[str, ToolSlice] = {}
        for e in tool_events:
            slice_ = by_tool.setdefault(e.tool, ToolSlice())
            slice_.calls += 1
            slice_.failures += 0 if e.ok else 1
            slice_.cache_hits += 1 if e.cached else 0
            tool_latencies[e.tool].append(e.latency_ms)
        for tool, slice_ in by_tool.items():
            slice_.p50_latency_ms = percentile(tool_latencies[tool], 0.50)
            slice_.p95_latency_ms = percentile(tool_latencies[tool], 0.95)

        failures_by_kind: dict[str, int] = defaultdict(int)
        for e in evs:
            if not e.ok and e.failure_kind:
                failures_by_kind[e.failure_kind] += 1

        total_usage = TokenUsage()
        for e in model_events:
            total_usage = total_usage + e.usage

        cacheable = len(tool_events)
        model_latencies = [e.latency_ms for e in model_events]

        return TelemetrySummary(
            total_model_calls=len(model_events),
            total_tool_calls=len(tool_events),
            total_usage=total_usage,
            total_estimated_cost_usd=sum(e.estimated_cost_usd for e in model_events),
            model_failure_rate=(
                sum(1 for e in model_events if not e.ok) / len(model_events)
                if model_events
                else 0.0
            ),
            tool_failure_rate=(
                sum(1 for e in tool_events if not e.ok) / len(tool_events)
                if tool_events
                else 0.0
            ),
            cache_hit_rate=(
                sum(1 for e in tool_events if e.cached) / cacheable if cacheable else 0.0
            ),
            p50_model_latency_ms=percentile(model_latencies, 0.50),
            p95_model_latency_ms=percentile(model_latencies, 0.95),
            by_model=by_model,
            by_tool=by_tool,
            failures_by_kind=dict(failures_by_kind),
        )


class RedisTelemetrySink:
    """Mirrors events into a capped Redis list for cross-process aggregation."""

    def __init__(self, redis: Any, key: str = "filing_intel:telemetry", cap: int = 10_000):
        self._redis = redis
        self._key = key
        self._cap = cap

    async def emit(self, event: TelemetryEvent) -> None:
        payload = json.dumps(event.model_dump(mode="json"), sort_keys=True)
        pipe = self._redis.pipeline()
        pipe.lpush(self._key, payload)
        pipe.ltrim(self._key, 0, self._cap - 1)
        await pipe.execute()
