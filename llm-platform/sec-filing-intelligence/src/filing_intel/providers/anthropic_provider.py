"""First-party Anthropic and Bedrock providers.

Both share request construction and response normalisation; they differ only in
which client class they instantiate and how model IDs are spelled. Bedrock is
partner-operated, so refusal fallbacks are handled client-side there rather than
with the server-side `fallbacks` parameter.
"""

from __future__ import annotations

import time
from typing import Any

import anthropic

from ..contracts import ModelResponse, TokenUsage, ToolCall
from ..errors import ProviderError, ProviderRefusal
from .base import (
    SERVER_SIDE_FALLBACK_BETA,
    ModelRequest,
    supports_adaptive_thinking,
    supports_refusal_fallback,
)


def _build_params(request: ModelRequest) -> dict[str, Any]:
    """Translate a `ModelRequest` into Messages API parameters.

    Notes on the current API that are easy to get wrong:
      * `effort` lives inside `output_config`, not at the top level.
      * `budget_tokens` is rejected with a 400 on every adaptive-thinking model;
        depth is controlled by effort instead.
      * `temperature`/`top_p` are removed on those models too, so we never send
        sampling parameters.
    """
    params: dict[str, Any] = {
        "model": request.model,
        "max_tokens": request.max_tokens,
        "messages": request.messages,
        "output_config": {"effort": request.effort},
    }

    if supports_adaptive_thinking(request.model):
        params["thinking"] = {"type": "adaptive"}

    if request.system is not None:
        params["system"] = request.system

    if request.tools:
        params["tools"] = [
            {
                "name": t.name,
                "description": t.description,
                "input_schema": t.input_schema,
                "strict": t.strict,
            }
            for t in request.tools
        ]

    if request.output_schema is not None:
        # Structured outputs live under `output_config.format`; the older
        # top-level `output_format` parameter is deprecated.
        params["output_config"]["format"] = {
            "type": "json_schema",
            "schema": request.output_schema,
        }

    if request.cache_prefix:
        # Caches the last cacheable block, which after tools+system is the
        # stable prefix shared by every turn in a session.
        params["cache_control"] = {"type": "ephemeral"}

    return params


def _normalize(
    message: Any, *, provider: str, model: str, latency_ms: float
) -> ModelResponse:
    """Turn an SDK `Message` into the provider-agnostic response."""
    stop_reason = getattr(message, "stop_reason", None)

    # `stop_details` is populated only on refusal; guard before reading it.
    if stop_reason == "refusal":
        details = getattr(message, "stop_details", None)
        category = getattr(details, "category", None) if details else None
        raise ProviderRefusal(
            f"model declined the request (category={category})", category=category
        )

    text_parts: list[str] = []
    tool_calls: list[ToolCall] = []
    raw_content: list[dict[str, Any]] = []

    for block in message.content:
        btype = getattr(block, "type", None)
        if btype == "text":
            text_parts.append(block.text)
        elif btype == "tool_use":
            tool_calls.append(
                # `input` is already parsed by the SDK; never string-match the
                # serialized form, escaping varies by model.
                ToolCall(id=block.id, name=block.name, arguments=dict(block.input))
            )
        if hasattr(block, "model_dump"):
            raw_content.append(block.model_dump())

    raw_usage = message.usage
    usage = TokenUsage(
        input_tokens=getattr(raw_usage, "input_tokens", 0) or 0,
        output_tokens=getattr(raw_usage, "output_tokens", 0) or 0,
        cache_read_input_tokens=getattr(raw_usage, "cache_read_input_tokens", 0) or 0,
        cache_creation_input_tokens=getattr(raw_usage, "cache_creation_input_tokens", 0) or 0,
    )

    return ModelResponse(
        text="\n".join(text_parts).strip(),
        tool_calls=tool_calls,
        stop_reason=stop_reason,
        usage=usage,
        model=getattr(message, "model", model),
        provider=provider,
        latency_ms=latency_ms,
        raw_content=raw_content,
    )


class AnthropicProvider:
    """Claude through the first-party API."""

    name = "anthropic"

    def __init__(self, client: Any | None = None) -> None:
        # Zero-arg construction resolves ANTHROPIC_API_KEY, ANTHROPIC_AUTH_TOKEN,
        # or an `ant auth login` profile, in that order.
        self._client = client or anthropic.AsyncAnthropic()

    async def complete(self, request: ModelRequest) -> ModelResponse:
        params = _build_params(request)
        started = time.perf_counter()
        try:
            if supports_refusal_fallback(request.model):
                # Route around a refusal server-side instead of surfacing it.
                message = await self._client.beta.messages.create(
                    **params, betas=[SERVER_SIDE_FALLBACK_BETA], fallbacks="default"
                )
            else:
                message = await self._client.messages.create(**params)
        except ProviderRefusal:
            raise
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"anthropic API error {exc.status_code}: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"anthropic connection error: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        return _normalize(
            message, provider=self.name, model=request.model, latency_ms=latency_ms
        )


class BedrockProvider:
    """Claude through AWS Bedrock.

    Model IDs carry an `anthropic.` prefix on Bedrock. Server-side refusal
    fallbacks are Claude-API-only, so a refusal propagates to the caller here.
    """

    name = "bedrock"

    def __init__(self, client: Any | None = None, aws_region: str = "us-east-1") -> None:
        if client is not None:
            self._client = client
        else:
            from anthropic import AsyncAnthropicBedrockMantle

            self._client = AsyncAnthropicBedrockMantle(aws_region=aws_region)

    @staticmethod
    def to_bedrock_model_id(model: str) -> str:
        return model if model.startswith("anthropic.") else f"anthropic.{model}"

    async def complete(self, request: ModelRequest) -> ModelResponse:
        params = _build_params(request)
        params["model"] = self.to_bedrock_model_id(request.model)
        started = time.perf_counter()
        try:
            message = await self._client.messages.create(**params)
        except ProviderRefusal:
            raise
        except anthropic.APIStatusError as exc:
            raise ProviderError(f"bedrock API error {exc.status_code}: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError(f"bedrock connection error: {exc}") from exc

        latency_ms = (time.perf_counter() - started) * 1000
        return _normalize(
            message, provider=self.name, model=request.model, latency_ms=latency_ms
        )
