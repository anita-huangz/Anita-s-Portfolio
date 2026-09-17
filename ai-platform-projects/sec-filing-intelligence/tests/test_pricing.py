"""Cost arithmetic. Getting this wrong misreports spend, silently."""

from __future__ import annotations

import pytest

from filing_intel.contracts import TokenUsage
from filing_intel.telemetry.pricing import (
    CACHE_READ_MULTIPLIER,
    CACHE_WRITE_MULTIPLIER,
    estimate_cost_usd,
    is_priced,
    normalize_model_id,
    rate_for,
)


def test_opus_5_rates():
    rate = rate_for("claude-opus-5")
    assert (rate.input_per_mtok, rate.output_per_mtok) == (5.00, 25.00)


def test_bedrock_prefix_maps_to_the_same_rate_row():
    assert normalize_model_id("anthropic.claude-opus-5") == "claude-opus-5"
    assert rate_for("anthropic.claude-opus-5") == rate_for("claude-opus-5")


def test_vertex_version_suffix_is_stripped():
    assert normalize_model_id("claude-opus-4-5@20251101") == "claude-opus-4-5"


def test_unknown_model_costs_zero_rather_than_raising():
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    assert estimate_cost_usd("some-unreleased-model", usage) == 0.0
    assert is_priced("some-unreleased-model") is False


def test_basic_cost_is_input_plus_output():
    usage = TokenUsage(input_tokens=1_000_000, output_tokens=1_000_000)
    # $5 in + $25 out
    assert estimate_cost_usd("claude-opus-5", usage) == pytest.approx(30.00)


def test_cached_reads_bill_off_the_input_rate_not_the_output_rate():
    """The classic error is billing cache tokens at the output rate."""
    usage = TokenUsage(cache_read_input_tokens=1_000_000)
    expected = 5.00 * CACHE_READ_MULTIPLIER
    assert estimate_cost_usd("claude-opus-5", usage) == pytest.approx(expected)
    # And it must be far cheaper than the same volume of fresh input.
    fresh = estimate_cost_usd("claude-opus-5", TokenUsage(input_tokens=1_000_000))
    assert estimate_cost_usd("claude-opus-5", usage) < fresh


def test_cache_writes_cost_more_than_fresh_input():
    written = estimate_cost_usd(
        "claude-opus-5", TokenUsage(cache_creation_input_tokens=1_000_000)
    )
    fresh = estimate_cost_usd("claude-opus-5", TokenUsage(input_tokens=1_000_000))
    assert written == pytest.approx(fresh * CACHE_WRITE_MULTIPLIER)


def test_sonnet_is_cheaper_than_opus_for_identical_usage():
    usage = TokenUsage(input_tokens=500_000, output_tokens=200_000)
    assert estimate_cost_usd("claude-sonnet-5", usage) < estimate_cost_usd(
        "claude-opus-5", usage
    )


def test_zero_usage_is_free():
    assert estimate_cost_usd("claude-opus-5", TokenUsage()) == 0.0
