"""Graph state and the prompts each node runs on."""

from __future__ import annotations

from typing import Any, TypedDict

from ..contracts import Capability, Finding, TokenUsage


class GraphState(TypedDict, total=False):
    # Inputs
    ticker: str
    question: str
    trace_id: str
    session_id: str
    capabilities: list[Capability]

    # Rolling conversation with the researcher, including tool results.
    messages: list[dict[str, Any]]
    # Tool calls the researcher asked for but that have not run yet. Must be a
    # declared key: LangGraph filters state down to the schema between nodes,
    # so an undeclared key silently vanishes on the next hop.
    pending_tool_calls: list[dict[str, Any]]

    # Node outputs
    plan: str
    tool_calls_made: int
    evidence: list[dict[str, Any]]
    answer: str
    findings: list[Finding]
    verified: bool
    verifier_note: str | None

    # Accounting
    usage: TokenUsage
    estimated_cost_usd: float
    failures: list[str]


PLANNER_SYSTEM = """You plan SEC-filing research.

Given a company and a question, write a short plan (3-5 numbered steps) naming \
which tools to call and in what order. Be specific about what evidence would \
actually answer the question.

Available evidence sources:
- search_filings: find accession numbers for a form type (10-K, 10-Q, 8-K, DEF 14A)
- fetch_filing_section: read business / risk_factors / mda / financial_statements
- company_financials: reported XBRL values for a US-GAAP concept across periods
- price_reaction: cumulative stock return over N trading days after an event

Output the plan only. Do not answer the question."""


RESEARCHER_SYSTEM = """You gather evidence from SEC filings to answer a question.

Work the plan by calling tools. Rules:
- Always call search_filings before any tool that needs an accession number.
- Prefer company_financials over reading numbers out of filing text.
- Stop calling tools as soon as you have enough to answer. Do not gather extra.
- If a tool returns an error, adapt: try a different form type, concept, or date \
rather than repeating the identical call.

When you have enough evidence, reply with a short prose summary of what you found \
and make no further tool calls."""


ANALYST_SYSTEM = """You turn gathered SEC-filing evidence into a cited answer.

Rules:
- Every factual claim must carry at least one citation to a filing you actually saw \
in the evidence. Cite the accession number and form type from the evidence.
- Do not invent accession numbers, dates, or figures. If the evidence does not \
support a claim, leave the claim out.
- Set confidence honestly: "high" only when a specific filing directly states it.
- The answer field is prose for a human; findings are the structured breakdown."""


VERIFIER_SYSTEM = """You audit a cited answer against the evidence that produced it.

Check every finding:
1. Does each cited accession number appear in the evidence?
2. Does the evidence actually support the claim, or is it an inference presented \
as fact?
3. Are any figures stated that do not appear in the evidence?

Be adversarial but fair. An answer that correctly says "the filings do not \
address this" is valid and should pass. Return verified=false only when a \
specific claim is unsupported, and say which one."""


ANALYST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "answer": {"type": "string"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "claim": {"type": "string"},
                    "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                    "citations": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "accession": {"type": "string"},
                                "form_type": {"type": "string"},
                                "filed_at": {"type": "string", "format": "date"},
                                "detail": {"type": "string"},
                            },
                            "required": ["accession", "form_type", "filed_at", "detail"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["claim", "confidence", "citations"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["answer", "findings"],
    "additionalProperties": False,
}


VERIFIER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verified": {"type": "boolean"},
        "note": {"type": "string"},
        "unsupported_claims": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["verified", "note", "unsupported_claims"],
    "additionalProperties": False,
}
