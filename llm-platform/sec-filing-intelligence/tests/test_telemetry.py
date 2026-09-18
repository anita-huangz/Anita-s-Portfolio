"""Aggregation: the numbers an operator would actually look at."""

from __future__ import annotations

import pytest

from filing_intel.contracts import TokenUsage
from filing_intel.telemetry import ModelCallEvent, TelemetryRecorder, ToolCallEvent, percentile


def model_event(**kw) -> ModelCallEvent:
    base = {
        "trace_id": "t1",
        "provider": "anthropic",
        "model": "claude-opus-5",
        "node": "researcher",
    }
    return ModelCallEvent(**{**base, **kw})


def tool_event(**kw) -> ToolCallEvent:
    return ToolCallEvent(**{"trace_id": "t1", "tool": "search_filings", **kw})


def test_percentile_on_empty_sample_is_zero():
    assert percentile([], 0.5) == 0.0


def test_percentile_nearest_rank():
    values = [10.0, 20.0, 30.0, 40.0, 50.0]
    assert percentile(values, 0.5) == 30.0
    assert percentile(values, 0.95) == 50.0


def test_percentile_ignores_input_ordering():
    assert percentile([50.0, 10.0, 30.0], 0.5) == 30.0


async def test_empty_summary_is_all_zeros():
    summary = TelemetryRecorder().summarize()
    assert summary.total_model_calls == 0
    assert summary.total_estimated_cost_usd == 0.0
    assert summary.model_failure_rate == 0.0
    assert summary.cache_hit_rate == 0.0


async def test_usage_and_cost_accumulate_across_calls():
    recorder = TelemetryRecorder()
    for _ in range(3):
        await recorder.record(
            model_event(
                usage=TokenUsage(input_tokens=100, output_tokens=50),
                estimated_cost_usd=0.002,
            )
        )
    summary = recorder.summarize()
    assert summary.total_model_calls == 3
    assert summary.total_usage.input_tokens == 300
    assert summary.total_usage.output_tokens == 150
    assert summary.total_estimated_cost_usd == pytest.approx(0.006)


async def test_spend_is_sliced_by_model():
    recorder = TelemetryRecorder()
    await recorder.record(model_event(model="claude-opus-5", estimated_cost_usd=0.10))
    await recorder.record(model_event(model="claude-sonnet-5", estimated_cost_usd=0.01))
    by_model = recorder.summarize().by_model
    assert by_model["claude-opus-5"].estimated_cost_usd == pytest.approx(0.10)
    assert by_model["claude-sonnet-5"].estimated_cost_usd == pytest.approx(0.01)


async def test_failure_rate_and_kinds():
    recorder = TelemetryRecorder()
    await recorder.record(model_event(ok=True))
    await recorder.record(model_event(ok=False, failure_kind="refusal"))
    await recorder.record(model_event(ok=False, failure_kind="provider"))
    summary = recorder.summarize()
    assert summary.model_failure_rate == pytest.approx(2 / 3)
    assert summary.failures_by_kind == {"refusal": 1, "provider": 1}


async def test_cache_hit_rate_counts_tool_calls_only():
    recorder = TelemetryRecorder()
    await recorder.record(tool_event(cached=True))
    await recorder.record(tool_event(cached=True))
    await recorder.record(tool_event(cached=False))
    await recorder.record(model_event())  # must not dilute the tool-cache rate
    summary = recorder.summarize()
    assert summary.total_tool_calls == 3
    assert summary.cache_hit_rate == pytest.approx(2 / 3)


async def test_tool_latency_percentiles():
    recorder = TelemetryRecorder()
    for ms in (10.0, 20.0, 30.0, 40.0, 1000.0):
        await recorder.record(tool_event(latency_ms=ms))
    slice_ = recorder.summarize().by_tool["search_filings"]
    assert slice_.p50_latency_ms == 30.0
    assert slice_.p95_latency_ms == 1000.0


async def test_buffer_is_bounded_and_drops_oldest():
    recorder = TelemetryRecorder(max_events=5)
    for i in range(20):
        await recorder.record(tool_event(tool=f"tool_{i}"))
    assert len(recorder.events) == 5
    assert recorder.events[-1].tool == "tool_19"


class CollectingSink:
    def __init__(self):
        self.emitted = []

    async def emit(self, event):
        self.emitted.append(event)


async def test_events_are_mirrored_to_the_sink():
    sink = CollectingSink()
    recorder = TelemetryRecorder(sink=sink)
    await recorder.record(model_event())
    assert len(sink.emitted) == 1
