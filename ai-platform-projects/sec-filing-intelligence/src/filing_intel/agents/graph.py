"""The multi-agent research workflow.

    plan -> research <-> tools -> analyze -> verify

`research` and `tools` form the agentic loop; every other node is a single
deterministic model call with a schema-constrained response. Bounded execution
is enforced in two places: `agent_max_tool_calls` caps the loop, and the tool
registry caps what the loop is allowed to reach.

Model calls go through the provider interface, so this graph is identical under
the live API and under recorded replay.
"""

from __future__ import annotations

import json
import time
from typing import Any

from langgraph.graph import END, StateGraph

from ..config import Settings
from ..contracts import Capability, Citation, Finding, ModelResponse, TokenUsage
from ..errors import ProviderError, ProviderRefusal
from ..providers.base import ModelProvider, ModelRequest
from ..telemetry import ModelCallEvent, TelemetryRecorder, estimate_cost_usd, is_priced
from ..tools import ToolRegistry
from .state import (
    ANALYST_SCHEMA,
    ANALYST_SYSTEM,
    PLANNER_SYSTEM,
    RESEARCHER_SYSTEM,
    VERIFIER_SCHEMA,
    VERIFIER_SYSTEM,
    GraphState,
)


class ResearchGraph:
    def __init__(
        self,
        provider: ModelProvider,
        registry: ToolRegistry,
        telemetry: TelemetryRecorder,
        settings: Settings,
    ) -> None:
        self._provider = provider
        self._registry = registry
        self._telemetry = telemetry
        self._settings = settings
        self._compiled = self._build()

    # ------------------------------------------------------------------ #
    # Model plumbing
    # ------------------------------------------------------------------ #

    async def _call_model(
        self, state: GraphState, node: str, request: ModelRequest
    ) -> ModelResponse | None:
        """Issue one model call, record telemetry, and fold usage into state.

        Returns None on failure. Nodes degrade rather than raise so a single bad
        call yields a partial, honestly-labelled answer instead of a 500.
        """
        started = time.perf_counter()
        try:
            response = await self._provider.complete(request)
        except (ProviderError, ProviderRefusal) as exc:
            latency_ms = (time.perf_counter() - started) * 1000
            await self._telemetry.record(
                ModelCallEvent(
                    trace_id=state["trace_id"],
                    session_id=state.get("session_id"),
                    provider=getattr(self._provider, "name", "unknown"),
                    model=request.model,
                    node=node,
                    latency_ms=latency_ms,
                    ok=False,
                    failure_kind=exc.kind,
                )
            )
            state.setdefault("failures", []).append(f"{node}: {exc.kind}: {exc}")
            return None

        cost = estimate_cost_usd(response.model or request.model, response.usage)
        await self._telemetry.record(
            ModelCallEvent(
                trace_id=state["trace_id"],
                session_id=state.get("session_id"),
                provider=response.provider or getattr(self._provider, "name", "unknown"),
                model=response.model or request.model,
                node=node,
                usage=response.usage,
                estimated_cost_usd=cost,
                cost_is_estimated=not is_priced(response.model or request.model),
                latency_ms=response.latency_ms,
                ok=True,
                stop_reason=response.stop_reason,
            )
        )
        state["usage"] = state.get("usage", TokenUsage()) + response.usage
        state["estimated_cost_usd"] = state.get("estimated_cost_usd", 0.0) + cost
        return response

    def _request(self, **kwargs: Any) -> ModelRequest:
        kwargs.setdefault("model", self._settings.model)
        kwargs.setdefault("effort", self._settings.effort)
        kwargs.setdefault("max_tokens", self._settings.max_tokens)
        return ModelRequest(**kwargs)

    # ------------------------------------------------------------------ #
    # Nodes
    # ------------------------------------------------------------------ #

    async def _plan(self, state: GraphState) -> GraphState:
        response = await self._call_model(
            state,
            "planner",
            self._request(
                system=PLANNER_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Company: {state['ticker']}\n"
                            f"Question: {state['question']}"
                        ),
                    }
                ],
                # A plan is short; spending high effort here buys nothing.
                effort="low",
            ),
        )
        plan = response.text if response else "Search recent filings and read the relevant section."
        state["plan"] = plan
        state["messages"] = [
            {
                "role": "user",
                "content": (
                    f"Company: {state['ticker']}\n"
                    f"Question: {state['question']}\n\n"
                    f"Research plan:\n{plan}"
                ),
            }
        ]
        state.setdefault("evidence", [])
        state.setdefault("tool_calls_made", 0)
        return state

    async def _research(self, state: GraphState) -> GraphState:
        specs = self._registry.specs_for(state["capabilities"])
        response = await self._call_model(
            state,
            "researcher",
            self._request(
                system=RESEARCHER_SYSTEM,
                messages=state["messages"],
                tools=specs,
            ),
        )
        if response is None:
            state["pending_tool_calls"] = []
            return state

        if response.raw_content:
            state["messages"] = [
                *state["messages"],
                {"role": "assistant", "content": response.raw_content},
            ]
        elif response.text:
            state["messages"] = [
                *state["messages"],
                {"role": "assistant", "content": response.text},
            ]

        state["pending_tool_calls"] = [
            call.model_dump() for call in response.tool_calls
        ]
        if not response.tool_calls and response.text:
            state["evidence"] = [
                *state.get("evidence", []),
                {"kind": "researcher_summary", "text": response.text},
            ]
        return state

    async def _run_tools(self, state: GraphState) -> GraphState:
        pending = state.get("pending_tool_calls", [])
        results: list[dict[str, Any]] = []

        for call in pending:
            result = await self._registry.execute(
                call["name"],
                call["arguments"],
                capabilities=state["capabilities"],
                trace_id=state["trace_id"],
                session_id=state.get("session_id"),
            )
            state["tool_calls_made"] = state.get("tool_calls_made", 0) + 1
            results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": call["id"],
                    "content": result.for_model(),
                    **({"is_error": True} if not result.ok else {}),
                }
            )
            state["evidence"] = [
                *state.get("evidence", []),
                {
                    "kind": "tool_result",
                    "tool": result.tool,
                    "ok": result.ok,
                    "arguments": call["arguments"],
                    "data": result.data if result.ok else result.error,
                },
            ]

        # All tool results for one assistant turn go back in a single user
        # message; splitting them trains the model out of parallel tool use.
        if results:
            state["messages"] = [*state["messages"], {"role": "user", "content": results}]
        state["pending_tool_calls"] = []
        return state

    async def _analyze(self, state: GraphState) -> GraphState:
        evidence_blob = json.dumps(state.get("evidence", []), default=str)[:60_000]
        response = await self._call_model(
            state,
            "analyst",
            self._request(
                system=ANALYST_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Question: {state['question']}\n"
                            f"Company: {state['ticker']}\n\n"
                            f"Evidence gathered:\n{evidence_blob}"
                        ),
                    }
                ],
                output_schema=ANALYST_SCHEMA,
            ),
        )
        if response is None:
            state["answer"] = (
                "Unable to produce an answer: the analysis step failed. "
                "See `failures` for the cause."
            )
            state["findings"] = []
            return state

        parsed = _parse_json(response.text)
        if parsed is None:
            state.setdefault("failures", []).append("analyst: response was not valid JSON")
            state["answer"] = response.text
            state["findings"] = []
            return state

        state["answer"] = parsed.get("answer", "")
        state["findings"] = _coerce_findings(parsed.get("findings", []))
        return state

    async def _verify(self, state: GraphState) -> GraphState:
        findings = state.get("findings", [])
        if not findings:
            state["verified"] = False
            state["verifier_note"] = "No findings to verify."
            return state

        evidence_blob = json.dumps(state.get("evidence", []), default=str)[:60_000]
        claims = json.dumps([f.model_dump(mode="json") for f in findings], default=str)
        response = await self._call_model(
            state,
            "verifier",
            self._request(
                system=VERIFIER_SYSTEM,
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Question: {state['question']}\n\n"
                            f"Findings to audit:\n{claims}\n\n"
                            f"Evidence available:\n{evidence_blob}"
                        ),
                    }
                ],
                output_schema=VERIFIER_SCHEMA,
                effort="medium",
            ),
        )
        if response is None:
            state["verified"] = False
            state["verifier_note"] = "Verification step failed; treat answer as unverified."
            return state

        parsed = _parse_json(response.text) or {}
        state["verified"] = bool(parsed.get("verified", False))
        note = parsed.get("note", "")
        unsupported = parsed.get("unsupported_claims") or []
        if unsupported:
            note = f"{note} Unsupported: {'; '.join(unsupported)}".strip()
        state["verifier_note"] = note or None
        return state

    # ------------------------------------------------------------------ #
    # Wiring
    # ------------------------------------------------------------------ #

    def _should_continue(self, state: GraphState) -> str:
        if state.get("pending_tool_calls"):
            if state.get("tool_calls_made", 0) >= self._settings.agent_max_tool_calls:
                # Bounded execution: stop looping and analyze what we have.
                state.setdefault("failures", []).append(
                    f"researcher: hit tool-call ceiling "
                    f"({self._settings.agent_max_tool_calls})"
                )
                return "analyze"
            return "tools"
        return "analyze"

    def _build(self):
        graph = StateGraph(GraphState)
        graph.add_node("plan", self._plan)
        graph.add_node("research", self._research)
        graph.add_node("tools", self._run_tools)
        graph.add_node("analyze", self._analyze)
        graph.add_node("verify", self._verify)

        graph.set_entry_point("plan")
        graph.add_edge("plan", "research")
        graph.add_conditional_edges(
            "research", self._should_continue, {"tools": "tools", "analyze": "analyze"}
        )
        graph.add_edge("tools", "research")
        graph.add_edge("analyze", "verify")
        graph.add_edge("verify", END)
        return graph.compile()

    async def run(self, state: GraphState) -> GraphState:
        # `recursion_limit` is LangGraph's own backstop; size it off the tool
        # ceiling so the graph's guard trips first and produces a real answer.
        return await self._compiled.ainvoke(
            state, config={"recursion_limit": self._settings.agent_max_tool_calls * 2 + 12}
        )


def _parse_json(text: str) -> dict[str, Any] | None:
    """Parse a model's JSON response, tolerating a code fence."""
    if not text:
        return None
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = candidate.split("\n", 1)[-1].rsplit("```", 1)[0]
    try:
        parsed = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def _coerce_findings(raw: list[Any]) -> list[Finding]:
    """Build Findings, dropping malformed ones rather than failing the request."""
    findings: list[Finding] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        citations = []
        for c in item.get("citations", []) or []:
            if not isinstance(c, dict):
                continue
            try:
                citations.append(Citation.model_validate(c))
            except ValueError:
                continue
        try:
            findings.append(
                Finding(
                    claim=item.get("claim", ""),
                    confidence=item.get("confidence", "low"),
                    citations=citations,
                )
            )
        except ValueError:
            continue
    return findings


__all__ = ["Capability", "ResearchGraph"]
