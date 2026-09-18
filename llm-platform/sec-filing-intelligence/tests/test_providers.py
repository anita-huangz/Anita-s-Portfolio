"""Provider layer: request shaping, response normalisation, replay determinism."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from filing_intel.contracts import ModelResponse, TokenUsage
from filing_intel.errors import ProviderRefusal, ReplayMiss
from filing_intel.providers import ModelRequest, ReplayProvider, ScriptedProvider, ToolSpec
from filing_intel.providers.anthropic_provider import (
    AnthropicProvider,
    BedrockProvider,
    _build_params,
    _normalize,
)
from filing_intel.providers.base import (
    supports_adaptive_thinking,
    supports_refusal_fallback,
)
from filing_intel.providers.replay import fixture_key

# --------------------------------------------------------------------------- #
# Fake SDK objects
# --------------------------------------------------------------------------- #


@dataclass
class FakeUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


@dataclass
class TextBlock:
    text: str
    type: str = "text"

    def model_dump(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict
    type: str = "tool_use"

    def model_dump(self) -> dict[str, Any]:
        return {"type": "tool_use", "id": self.id, "name": self.name, "input": self.input}


@dataclass
class StopDetails:
    category: str
    type: str = "refusal"


@dataclass
class FakeMessage:
    content: list = field(default_factory=list)
    usage: FakeUsage = field(default_factory=FakeUsage)
    stop_reason: str = "end_turn"
    model: str = "claude-opus-5"
    stop_details: Any = None


class RecordingClient:
    """Captures the kwargs the provider would send to the SDK."""

    def __init__(self, message: FakeMessage):
        self._message = message
        self.calls: list[dict] = []
        self.messages = self._Messages(self)
        self.beta = self._Beta(self)

    class _Messages:
        def __init__(self, outer):
            self._outer = outer

        async def create(self, **kwargs):
            self._outer.calls.append({"path": "stable", **kwargs})
            return self._outer._message

    class _Beta:
        def __init__(self, outer):
            self.messages = RecordingClient._BetaMessages(outer)

    class _BetaMessages:
        def __init__(self, outer):
            self._outer = outer

        async def create(self, **kwargs):
            self._outer.calls.append({"path": "beta", **kwargs})
            return self._outer._message


# --------------------------------------------------------------------------- #
# Request shaping
# --------------------------------------------------------------------------- #


def request(**kw) -> ModelRequest:
    return ModelRequest(
        **{"model": "claude-opus-5", "messages": [{"role": "user", "content": "hi"}], **kw}
    )


def test_effort_goes_inside_output_config_not_top_level():
    params = _build_params(request(effort="xhigh"))
    assert params["output_config"]["effort"] == "xhigh"
    assert "effort" not in params


def test_adaptive_thinking_is_set_and_budget_tokens_never_is():
    params = _build_params(request())
    assert params["thinking"] == {"type": "adaptive"}
    # budget_tokens is rejected with a 400 on every adaptive-thinking model.
    assert "budget_tokens" not in str(params)


def test_no_sampling_parameters_are_sent():
    """temperature/top_p/top_k are removed on current models and 400."""
    params = _build_params(request())
    assert not {"temperature", "top_p", "top_k"} & set(params)


def test_haiku_does_not_get_adaptive_thinking():
    params = _build_params(request(model="claude-haiku-4-5"))
    assert "thinking" not in params


def test_tools_are_rendered_strict():
    spec = ToolSpec(
        name="t", description="d",
        input_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )
    params = _build_params(request(tools=[spec]))
    assert params["tools"][0]["strict"] is True
    assert params["tools"][0]["name"] == "t"


def test_output_schema_becomes_output_config_format():
    schema = {"type": "object", "properties": {}, "additionalProperties": False}
    params = _build_params(request(output_schema=schema))
    assert params["output_config"]["format"] == {"type": "json_schema", "schema": schema}
    # The deprecated top-level parameter must not be used.
    assert "output_format" not in params


def test_cache_control_is_on_by_default_and_can_be_disabled():
    assert _build_params(request())["cache_control"] == {"type": "ephemeral"}
    assert "cache_control" not in _build_params(request(cache_prefix=False))


@pytest.mark.parametrize(
    "model,adaptive", [("claude-opus-5", True), ("claude-haiku-4-5", False)]
)
def test_adaptive_thinking_support_table(model, adaptive):
    assert supports_adaptive_thinking(model) is adaptive


def test_bedrock_prefixed_ids_resolve_to_the_same_capabilities():
    assert supports_adaptive_thinking("anthropic.claude-opus-5") is True
    assert supports_refusal_fallback("anthropic.claude-opus-5") is True


# --------------------------------------------------------------------------- #
# Response normalisation
# --------------------------------------------------------------------------- #


def test_text_and_tool_calls_are_extracted():
    message = FakeMessage(
        content=[
            TextBlock("thinking out loud"),
            ToolUseBlock(id="tu_1", name="search_filings", input={"ticker": "AAPL"}),
        ],
        usage=FakeUsage(input_tokens=10, output_tokens=5, cache_read_input_tokens=3),
        stop_reason="tool_use",
    )
    response = _normalize(message, provider="anthropic", model="claude-opus-5", latency_ms=12.0)
    assert response.text == "thinking out loud"
    assert response.tool_calls[0].name == "search_filings"
    assert response.tool_calls[0].arguments == {"ticker": "AAPL"}
    assert response.usage.cache_read_input_tokens == 3
    assert response.latency_ms == 12.0
    # raw_content is replayed verbatim on the next turn.
    assert response.raw_content[1]["type"] == "tool_use"


def test_refusal_stop_reason_raises_with_its_category():
    message = FakeMessage(stop_reason="refusal", stop_details=StopDetails(category="cyber"))
    with pytest.raises(ProviderRefusal) as exc:
        _normalize(message, provider="anthropic", model="claude-opus-5", latency_ms=1.0)
    assert exc.value.category == "cyber"


def test_missing_usage_fields_default_to_zero():
    response = _normalize(
        FakeMessage(content=[TextBlock("hi")]),
        provider="anthropic", model="claude-opus-5", latency_ms=1.0,
    )
    assert response.usage.total == 0


# --------------------------------------------------------------------------- #
# Routing
# --------------------------------------------------------------------------- #


async def test_opus_5_routes_through_beta_with_refusal_fallbacks():
    client = RecordingClient(FakeMessage(content=[TextBlock("ok")]))
    await AnthropicProvider(client=client).complete(request(model="claude-opus-5"))
    call = client.calls[0]
    assert call["path"] == "beta"
    assert call["fallbacks"] == "default"
    assert call["betas"] == ["server-side-fallback-2026-07-01"]


async def test_model_without_refusal_fallback_uses_the_stable_endpoint():
    client = RecordingClient(FakeMessage(content=[TextBlock("ok")]))
    await AnthropicProvider(client=client).complete(request(model="claude-haiku-4-5"))
    assert client.calls[0]["path"] == "stable"
    assert "fallbacks" not in client.calls[0]


async def test_bedrock_prefixes_the_model_id():
    client = RecordingClient(FakeMessage(content=[TextBlock("ok")]))
    provider = BedrockProvider(client=client)
    await provider.complete(request(model="claude-opus-5"))
    assert client.calls[0]["model"] == "anthropic.claude-opus-5"


def test_bedrock_does_not_double_prefix():
    assert (
        BedrockProvider.to_bedrock_model_id("anthropic.claude-opus-5")
        == "anthropic.claude-opus-5"
    )


# --------------------------------------------------------------------------- #
# Replay
# --------------------------------------------------------------------------- #


def test_fixture_key_is_stable_across_identical_requests():
    assert fixture_key(request()) == fixture_key(request())


def test_fixture_key_ignores_billing_only_fields():
    """max_tokens changes cost and truncation, not which answer a fixture is."""
    assert fixture_key(request(max_tokens=100)) == fixture_key(request(max_tokens=9999))


def test_fixture_key_changes_with_messages_model_and_effort():
    base = fixture_key(request())
    assert fixture_key(request(model="claude-sonnet-5")) != base
    assert fixture_key(request(effort="low")) != base
    assert fixture_key(request(messages=[{"role": "user", "content": "other"}])) != base


async def test_replay_miss_is_explicit_about_how_to_fix_it(tmp_path):
    provider = ReplayProvider(tmp_path)
    with pytest.raises(ReplayMiss, match="REPLAY_RECORD"):
        await provider.complete(request())


async def test_recorded_response_replays_identically(tmp_path):
    upstream = ScriptedProvider(
        [ModelResponse(
            text="recorded answer",
            usage=TokenUsage(input_tokens=42, output_tokens=7),
            model="claude-opus-5",
            provider="anthropic",
        )]
    )
    recording = ReplayProvider(tmp_path, record_with=upstream)
    first = await recording.complete(request())

    # A fresh provider with no upstream must serve the same response from disk.
    replaying = ReplayProvider(tmp_path)
    second = await replaying.complete(request())

    assert second.text == first.text == "recorded answer"
    assert second.usage.input_tokens == 42
    assert len(upstream.calls) == 1  # upstream hit once, not twice
