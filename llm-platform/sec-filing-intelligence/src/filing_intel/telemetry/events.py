"""Typed telemetry events.

One event per model call and per tool call. Every field is low-cardinality
except `trace_id`/`session_id`, so events aggregate cleanly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import Field

from ..contracts import Strict, TokenUsage, utcnow

EventType = Literal["model_call", "tool_call"]


class ModelCallEvent(Strict):
    type: Literal["model_call"] = "model_call"
    at: datetime = Field(default_factory=utcnow)
    trace_id: str
    session_id: str | None = None
    provider: str
    model: str
    node: str = Field(description="Which agent node issued the call.")
    usage: TokenUsage = Field(default_factory=TokenUsage)
    estimated_cost_usd: float = 0.0
    cost_is_estimated: bool = False
    latency_ms: float = 0.0
    ok: bool = True
    failure_kind: str | None = None
    stop_reason: str | None = None
    cached: bool = False


class ToolCallEvent(Strict):
    type: Literal["tool_call"] = "tool_call"
    at: datetime = Field(default_factory=utcnow)
    trace_id: str
    session_id: str | None = None
    tool: str
    latency_ms: float = 0.0
    ok: bool = True
    failure_kind: str | None = None
    cached: bool = False


TelemetryEvent = ModelCallEvent | ToolCallEvent
