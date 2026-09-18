"""The common model-access interface.

Everything above this layer speaks `ModelRequest` / `ModelResponse` and never
imports a vendor SDK. That is what makes the replay provider a drop-in for the
real one, and what keeps the agent graph free of provider branching.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from pydantic import Field

from ..contracts import ModelResponse, Strict

#: Models where thinking is adaptive and `budget_tokens` is rejected with a 400.
ADAPTIVE_THINKING_MODELS = frozenset(
    {
        "claude-fable-5-1",
        "claude-fable-5",
        "claude-mythos-5-1",
        "claude-opus-5",
        "claude-opus-4-8",
        "claude-opus-4-7",
        "claude-opus-4-6",
        "claude-sonnet-5",
        "claude-sonnet-4-6",
    }
)

#: Models that can return `stop_reason == "refusal"` and support server-side
#: refusal fallbacks.
REFUSAL_FALLBACK_MODELS = frozenset(
    {"claude-fable-5-1", "claude-fable-5", "claude-mythos-5-1", "claude-opus-5"}
)

SERVER_SIDE_FALLBACK_BETA = "server-side-fallback-2026-07-01"


class ToolSpec(Strict):
    """A tool as the model sees it."""

    name: str
    description: str
    input_schema: dict[str, Any]
    strict: bool = True


class ModelRequest(Strict):
    model: str
    messages: list[dict[str, Any]]
    system: str | list[dict[str, Any]] | None = None
    tools: list[ToolSpec] = Field(default_factory=list)
    max_tokens: int = 16000
    effort: str = "high"
    #: JSON Schema the response must conform to, via `output_config.format`.
    #: Mutually exclusive with tools in practice -- ask for one or the other.
    output_schema: dict[str, Any] | None = None
    #: Cache the stable prefix (tools + system) across turns of a session.
    cache_prefix: bool = True


@runtime_checkable
class ModelProvider(Protocol):
    """Implemented by every backend: Anthropic, Bedrock, and replay."""

    name: str

    async def complete(self, request: ModelRequest) -> ModelResponse: ...


def supports_adaptive_thinking(model: str) -> bool:
    return _bare(model) in ADAPTIVE_THINKING_MODELS


def supports_refusal_fallback(model: str) -> bool:
    return _bare(model) in REFUSAL_FALLBACK_MODELS


def _bare(model: str) -> str:
    return model.removeprefix("anthropic.").split("@", 1)[0]
