"""The multi-agent workflow, driven by scripted model responses.

Every node, edge, and bound is exercised here without touching the network, so
CI proves the orchestration logic rather than the model's taste.
"""

from __future__ import annotations

import json

import pytest

from conftest import text_response, tool_response
from filing_intel.agents import ResearchGraph
from filing_intel.contracts import Capability, ResearchRequest, TokenUsage
from filing_intel.errors import ProviderError, ProviderRefusal
from filing_intel.providers import ScriptedProvider
from filing_intel.runtime import FilingIntelRuntime

ANALYST_JSON = json.dumps(
    {
        "answer": "Apple flags supply-chain concentration as a principal risk.",
        "findings": [
            {
                "claim": "Apple depends on a small number of manufacturing partners.",
                "confidence": "high",
                "citations": [
                    {
                        "accession": "0000320193-23-000106",
                        "form_type": "10-K",
                        "filed_at": "2023-11-03",
                        "detail": "Item 1A, Risk Factors",
                    }
                ],
            }
        ],
    }
)

VERIFIER_JSON = json.dumps(
    {"verified": True, "note": "Citation matches the fetched section.", "unsupported_claims": []}
)


def build(settings, registry, telemetry, responses) -> ResearchGraph:
    return ResearchGraph(ScriptedProvider(responses), registry, telemetry, settings)


def base_state(**kw):
    return {
        "ticker": "AAPL",
        "question": "What supply-chain risks does Apple disclose?",
        "trace_id": "trace-1",
        "session_id": "sess-1",
        "capabilities": list(Capability),
        "usage": TokenUsage(),
        "estimated_cost_usd": 0.0,
        "failures": [],
        **kw,
    }


async def test_full_path_plan_research_tools_analyze_verify(
    settings, registry, telemetry, edgar
):
    graph = build(
        settings, registry, telemetry,
        [
            text_response("1. search_filings 2. fetch risk_factors"),   # planner
            tool_response("search_filings", {"ticker": "AAPL"}),         # researcher
            tool_response(
                "fetch_filing_section",
                {"ticker": "AAPL", "accession": "0000320193-23-000106",
                 "section": "risk_factors"},
                call_id="tu_2",
            ),
            text_response("Found the risk factors section."),            # researcher done
            text_response(ANALYST_JSON),                                  # analyst
            text_response(VERIFIER_JSON),                                 # verifier
        ],
    )
    state = await graph.run(base_state())

    assert state["tool_calls_made"] == 2
    assert "supply-chain concentration" in state["answer"]
    assert state["findings"][0].confidence == "high"
    assert state["findings"][0].citations[0].accession == "0000320193-23-000106"
    assert state["verified"] is True
    assert state["failures"] == []
    # Both tools actually reached the data layer.
    assert [c[0] for c in edgar.calls] == ["search_filings", "fetch_section"]


async def test_researcher_with_no_tool_calls_goes_straight_to_analysis(
    settings, registry, telemetry, edgar
):
    graph = build(
        settings, registry, telemetry,
        [
            text_response("plan"),
            text_response("I can answer from general knowledge."),
            text_response(ANALYST_JSON),
            text_response(VERIFIER_JSON),
        ],
    )
    state = await graph.run(base_state())
    assert state["tool_calls_made"] == 0
    assert edgar.calls == []
    assert state["verified"] is True


async def test_tool_call_ceiling_stops_the_loop_and_still_answers(
    settings, registry, telemetry
):
    """Bounded execution: an unproductive loop must terminate with an answer."""
    settings.agent_max_tool_calls = 3
    responses = [text_response("plan")]
    # The researcher keeps asking for tools and never volunteers to stop. It is
    # called once more than the ceiling: the guard trips on the call that would
    # have exceeded it.
    for i in range(settings.agent_max_tool_calls + 1):
        responses.append(tool_response("search_filings", {"ticker": "AAPL"}, f"tu_{i}"))
    responses += [text_response(ANALYST_JSON), text_response(VERIFIER_JSON)]

    state = await build(settings, registry, telemetry, responses).run(base_state())

    assert state["tool_calls_made"] == 3
    assert any("ceiling" in f for f in state["failures"])
    assert state["answer"]  # still produced a result


async def test_usage_and_cost_accumulate_across_every_node(
    settings, registry, telemetry
):
    graph = build(
        settings, registry, telemetry,
        [
            text_response("plan", usage=TokenUsage(input_tokens=100, output_tokens=10)),
            text_response("done", usage=TokenUsage(input_tokens=200, output_tokens=20)),
            text_response(ANALYST_JSON, usage=TokenUsage(input_tokens=300, output_tokens=30)),
            text_response(VERIFIER_JSON, usage=TokenUsage(input_tokens=400, output_tokens=40)),
        ],
    )
    state = await graph.run(base_state())

    assert state["usage"].input_tokens == 1000
    assert state["usage"].output_tokens == 100
    # 1000 in @ $5/Mtok + 100 out @ $25/Mtok
    assert state["estimated_cost_usd"] == pytest.approx(1000 * 5e-6 + 100 * 25e-6)


async def test_tool_failure_is_fed_back_to_the_model_as_an_error_result(
    settings, registry, telemetry
):
    graph = build(
        settings, registry, telemetry,
        [
            text_response("plan"),
            tool_response("search_filings", {"ticker": "ZZZZ"}),  # unknown registrant
            text_response("That ticker is not a registrant."),
            text_response(ANALYST_JSON),
            text_response(VERIFIER_JSON),
        ],
    )
    state = await graph.run(base_state())

    tool_evidence = next(e for e in state["evidence"] if e["kind"] == "tool_result")
    assert tool_evidence["ok"] is False
    # The error came back as a tool_result block flagged is_error, not a crash.
    tool_msg = next(
        m for m in state["messages"]
        if isinstance(m.get("content"), list)
        and any(b.get("type") == "tool_result" for b in m["content"])
    )
    assert tool_msg["content"][0]["is_error"] is True


async def test_capability_denial_does_not_abort_the_run(settings, registry, telemetry):
    graph = build(
        settings, registry, telemetry,
        [
            text_response("plan"),
            tool_response("price_reaction", {"ticker": "AAPL", "event_date": "2023-11-03"}),
            text_response("No price access; answering from filings."),
            text_response(ANALYST_JSON),
            text_response(VERIFIER_JSON),
        ],
    )
    state = await graph.run(base_state(capabilities=[Capability.READ_FILINGS]))

    denied = next(e for e in state["evidence"] if e["kind"] == "tool_result")
    assert denied["ok"] is False
    assert state["answer"]


async def test_provider_failure_degrades_to_a_partial_answer(
    settings, registry, telemetry
):
    class FailingProvider:
        name = "failing"

        def __init__(self):
            self.n = 0

        async def complete(self, request):
            self.n += 1
            if self.n == 1:
                return text_response("plan")
            raise ProviderError("upstream 503")

    graph = ResearchGraph(FailingProvider(), registry, telemetry, settings)
    state = await graph.run(base_state())

    assert state["verified"] is False
    assert "Unable to produce an answer" in state["answer"]
    assert any("provider" in f for f in state["failures"])


async def test_refusal_is_recorded_as_its_own_failure_kind(
    settings, registry, telemetry
):
    class RefusingProvider:
        name = "refusing"

        async def complete(self, request):
            raise ProviderRefusal("declined", category="cyber")

    graph = ResearchGraph(RefusingProvider(), registry, telemetry, settings)
    await graph.run(base_state())
    assert telemetry.summarize().failures_by_kind.get("refusal", 0) > 0


async def test_non_json_analyst_output_is_surfaced_not_swallowed(
    settings, registry, telemetry
):
    graph = build(
        settings, registry, telemetry,
        [
            text_response("plan"),
            text_response("done"),
            text_response("I am prose, not JSON."),
            text_response(VERIFIER_JSON),
        ],
    )
    state = await graph.run(base_state())
    assert any("not valid JSON" in f for f in state["failures"])
    assert state["findings"] == []


async def test_fenced_json_is_still_parsed(settings, registry, telemetry):
    graph = build(
        settings, registry, telemetry,
        [
            text_response("plan"),
            text_response("done"),
            text_response(f"```json\n{ANALYST_JSON}\n```"),
            text_response(VERIFIER_JSON),
        ],
    )
    state = await graph.run(base_state())
    assert len(state["findings"]) == 1


async def test_malformed_findings_are_dropped_individually(
    settings, registry, telemetry
):
    mixed = json.dumps(
        {
            "answer": "ok",
            "findings": [
                {"claim": "good", "confidence": "high", "citations": []},
                {"claim": "bad confidence", "confidence": "certain", "citations": []},
                "not even an object",
            ],
        }
    )
    graph = build(
        settings, registry, telemetry,
        [text_response("plan"), text_response("done"), text_response(mixed),
         text_response(VERIFIER_JSON)],
    )
    state = await graph.run(base_state())
    assert [f.claim for f in state["findings"]] == ["good"]


async def test_verifier_rejection_is_reported(settings, registry, telemetry):
    rejection = json.dumps(
        {"verified": False, "note": "Citation not in evidence.",
         "unsupported_claims": ["Apple depends on a small number of partners."]}
    )
    graph = build(
        settings, registry, telemetry,
        [text_response("plan"), text_response("done"), text_response(ANALYST_JSON),
         text_response(rejection)],
    )
    state = await graph.run(base_state())
    assert state["verified"] is False
    assert "Unsupported:" in state["verifier_note"]


async def test_telemetry_attributes_each_call_to_its_node(
    settings, registry, telemetry
):
    graph = build(
        settings, registry, telemetry,
        [text_response("plan"), text_response("done"), text_response(ANALYST_JSON),
         text_response(VERIFIER_JSON)],
    )
    await graph.run(base_state())
    nodes = [e.node for e in telemetry.events if e.type == "model_call"]
    assert nodes == ["planner", "researcher", "analyst", "verifier"]


async def test_planner_uses_low_effort_to_avoid_paying_for_a_plan(
    settings, registry, telemetry
):
    provider = ScriptedProvider(
        [text_response("plan"), text_response("done"), text_response(ANALYST_JSON),
         text_response(VERIFIER_JSON)]
    )
    await ResearchGraph(provider, registry, telemetry, settings).run(base_state())
    assert provider.calls[0].effort == "low"
    assert provider.calls[2].effort == settings.effort  # analyst gets full effort


async def test_researcher_is_the_only_node_given_tools(settings, registry, telemetry):
    provider = ScriptedProvider(
        [text_response("plan"), text_response("done"), text_response(ANALYST_JSON),
         text_response(VERIFIER_JSON)]
    )
    await ResearchGraph(provider, registry, telemetry, settings).run(base_state())
    assert provider.calls[0].tools == []
    assert len(provider.calls[1].tools) == 4
    assert provider.calls[2].tools == []
    # Analyst and verifier constrain their output with a schema instead.
    assert provider.calls[2].output_schema is not None
    assert provider.calls[3].output_schema is not None


# --------------------------------------------------------------------------- #
# Runtime integration
# --------------------------------------------------------------------------- #


async def test_runtime_research_returns_a_populated_response(
    settings, edgar, prices, cache, telemetry
):
    provider = ScriptedProvider(
        [text_response("plan"), text_response("done"), text_response(ANALYST_JSON),
         text_response(VERIFIER_JSON)]
    )
    runtime = FilingIntelRuntime(settings, provider, cache, edgar, prices, telemetry)
    response = await runtime.research(
        ResearchRequest(ticker="AAPL", question="What are the supply-chain risks?")
    )

    assert response.verified is True
    assert response.estimated_cost_usd > 0
    assert response.latency_ms > 0
    assert response.trace_id
    assert len(response.findings) == 1


async def test_session_accumulates_across_turns(
    settings, edgar, prices, cache, telemetry
):
    def script():
        return [text_response("plan"), text_response("done"),
                text_response(ANALYST_JSON), text_response(VERIFIER_JSON)]

    runtime = FilingIntelRuntime(
        settings, ScriptedProvider(script() * 2), cache, edgar, prices, telemetry
    )
    first = await runtime.research(ResearchRequest(ticker="AAPL", question="Question one?"))
    await runtime.research(
        ResearchRequest(ticker="AAPL", question="Question two?", session_id=first.session_id)
    )

    session = await runtime.sessions.get(first.session_id)
    assert session.turns == 2
    assert session.estimated_cost_usd == pytest.approx(first.estimated_cost_usd * 2)
