"""Token -> USD.

Rates are Anthropic first-party list prices per 1M tokens, as published on
2026-06-24. Bedrock and Vertex are partner-operated and priced separately, so a
cost computed for a Bedrock call is an estimate against first-party rates and is
labelled as such on the telemetry event.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..contracts import TokenUsage

# Cache reads bill at ~0.1x the input rate; cache writes at ~1.25x.
CACHE_READ_MULTIPLIER = 0.10
CACHE_WRITE_MULTIPLIER = 1.25


@dataclass(frozen=True)
class ModelRate:
    input_per_mtok: float
    output_per_mtok: float


# Keep exact model IDs. They are complete as-is -- never append a date suffix.
RATES: dict[str, ModelRate] = {
    "claude-fable-5-1": ModelRate(10.00, 50.00),
    "claude-fable-5": ModelRate(10.00, 50.00),
    "claude-mythos-5-1": ModelRate(10.00, 50.00),
    "claude-opus-5": ModelRate(5.00, 25.00),
    "claude-opus-4-8": ModelRate(5.00, 25.00),
    "claude-opus-4-7": ModelRate(5.00, 25.00),
    "claude-opus-4-6": ModelRate(5.00, 25.00),
    "claude-sonnet-5": ModelRate(2.00, 10.00),
    "claude-sonnet-4-6": ModelRate(3.00, 15.00),
    "claude-haiku-4-5": ModelRate(1.00, 5.00),
}

#: Returned for an unknown model so cost tracking degrades to zero rather than
#: crashing a request. `is_estimated` on the event flags it for the operator.
UNKNOWN_RATE = ModelRate(0.0, 0.0)


def normalize_model_id(model: str) -> str:
    """Strip platform prefixes so Bedrock and first-party IDs share a rate row."""
    return model.removeprefix("anthropic.").split("@", 1)[0]


def rate_for(model: str) -> ModelRate:
    return RATES.get(normalize_model_id(model), UNKNOWN_RATE)


def is_priced(model: str) -> bool:
    return normalize_model_id(model) in RATES


def estimate_cost_usd(model: str, usage: TokenUsage) -> float:
    """Cost of a single call in USD.

    Cached-read and cache-write tokens are billed off the *input* rate, not the
    output rate -- getting that backwards is the usual way these tables end up
    overstating spend on cache-heavy workloads.
    """
    rate = rate_for(model)
    per_input_token = rate.input_per_mtok / 1_000_000
    per_output_token = rate.output_per_mtok / 1_000_000

    return (
        usage.input_tokens * per_input_token
        + usage.output_tokens * per_output_token
        + usage.cache_read_input_tokens * per_input_token * CACHE_READ_MULTIPLIER
        + usage.cache_creation_input_tokens * per_input_token * CACHE_WRITE_MULTIPLIER
    )
