"""A deterministic stand-in for the model, for running the harness without a key.

What this is honest about: it measures the *orchestration* -- tool routing,
capability enforcement, caching, telemetry, cost accounting, the verifier gate --
against real SEC EDGAR data. It does not measure model quality, because there is
no model in the loop. Accuracy reported in offline mode is the harness grading
the platform's plumbing, not Claude's answers.

To measure real accuracy, record fixtures against the live API:

    FILING_INTEL_PROVIDER=replay FILING_INTEL_REPLAY_RECORD=true \
    ANTHROPIC_API_KEY=... python -m evals.harness --repeats 1

and then re-run with `FILING_INTEL_REPLAY_RECORD=false` for a free, deterministic
replay of those same responses.
"""

from __future__ import annotations

import json
import re
from typing import Any

from filing_intel.contracts import ModelResponse, TokenUsage, ToolCall
from filing_intel.providers.base import ModelRequest

_ACCESSION_RE = re.compile(r"\d{10}-\d{2}-\d{6}")


class OfflineProvider:
    """Routes on the system prompt to decide which node is asking."""

    name = "offline-stub"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        system = str(request.system or "")

        if system.startswith("You plan SEC-filing research"):
            return self._response("1. search_filings\n2. read the relevant section", 120, 40)
        if system.startswith("You gather evidence"):
            return self._research(request)
        if system.startswith("You turn gathered"):
            return self._analyze(request)
        return self._verify(request)

    # ------------------------------------------------------------------ #

    @staticmethod
    def _response(text: str, in_tok: int, out_tok: int, **kw: Any) -> ModelResponse:
        return ModelResponse(
            text=text,
            model="claude-opus-5",
            provider="offline-stub",
            usage=TokenUsage(input_tokens=in_tok, output_tokens=out_tok),
            stop_reason=kw.pop("stop_reason", "end_turn"),
            **kw,
        )

    def _research(self, request: ModelRequest) -> ModelResponse:
        """Walk a fixed policy: find filings, then fetch whatever the question needs."""
        transcript = json.dumps(request.messages, default=str)
        ticker = _ticker(transcript)
        question = transcript.lower()
        available = {t.name for t in request.tools}
        # Detect prior calls from actual tool_use blocks. A substring scan over
        # the transcript would also match the planner's prose, which names the
        # tools it intends to use, and the researcher would never call anything.
        called = _tools_already_called(request.messages)

        if "search_filings" not in called and "search_filings" in available:
            return self._tool("search_filings", {"ticker": ticker, "limit": 3}, "tu_search")

        accession = _first_accession(transcript)

        wants_numbers = any(w in question for w in ("revenue", "income", "margin trend"))
        if (
            wants_numbers
            and "company_financials" in available
            and "company_financials" not in called
        ):
            return self._tool(
                "company_financials",
                {"ticker": ticker, "concept": "Revenues", "periods": 4},
                "tu_facts",
            )

        wants_reaction = any(w in question for w in ("react", "stock", "trading days"))
        if wants_reaction and "price_reaction" in available and "price_reaction" not in called:
            filed = _first_date(transcript)
            if filed:
                return self._tool(
                    "price_reaction",
                    {"ticker": ticker, "event_date": filed, "horizons": [1, 5]},
                    "tu_price",
                )

        if (
            accession
            and "fetch_filing_section" in available
            and "fetch_filing_section" not in called
        ):
            section = "mda" if "md&a" in question or "margin" in question else "risk_factors"
            return self._tool(
                "fetch_filing_section",
                {"ticker": ticker, "accession": accession, "section": section,
                 "max_chars": 4000},
                "tu_section",
            )

        return self._response("Gathered the available evidence.", 800, 60)

    def _tool(self, name: str, arguments: dict, call_id: str) -> ModelResponse:
        return ModelResponse(
            text="",
            tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
            stop_reason="tool_use",
            model="claude-opus-5",
            provider="offline-stub",
            usage=TokenUsage(input_tokens=600, output_tokens=45),
            raw_content=[
                {"type": "tool_use", "id": call_id, "name": name, "input": arguments}
            ],
        )

    def _analyze(self, request: ModelRequest) -> ModelResponse:
        blob = json.dumps(request.messages, default=str)
        accession = _first_accession(blob)
        filed = _first_date(blob) or "2023-01-01"

        if not accession:
            # Nothing was retrieved -- say so rather than inventing a citation.
            return self._response(
                json.dumps(
                    {
                        "answer": "The filings retrieved do not address this question.",
                        "findings": [],
                    }
                ),
                1500, 90,
            )

        return self._response(
            json.dumps(
                {
                    "answer": (
                        "Based on the retrieved filing, the company discloses the "
                        "relevant material in the cited section."
                    ),
                    "findings": [
                        {
                            "claim": "The cited filing addresses the question.",
                            "confidence": "medium",
                            "citations": [
                                {
                                    "accession": accession,
                                    "form_type": "10-K",
                                    "filed_at": filed,
                                    "detail": "Retrieved section",
                                }
                            ],
                        }
                    ],
                }
            ),
            2400, 180,
        )

    def _verify(self, request: ModelRequest) -> ModelResponse:
        blob = json.dumps(request.messages, default=str)
        cited = set(_ACCESSION_RE.findall(blob))
        return self._response(
            json.dumps(
                {
                    "verified": bool(cited),
                    "note": "Citations cross-checked against gathered evidence."
                    if cited
                    else "No citations to check.",
                    "unsupported_claims": [],
                }
            ),
            1800, 70,
        )


def _tools_already_called(messages: list[dict[str, Any]]) -> set[str]:
    """Names of tools invoked so far, read off the assistant tool_use blocks."""
    names: set[str] = set()
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                names.add(block.get("name", ""))
    return names


def _ticker(transcript: str) -> str:
    match = re.search(r"Company: ([A-Z.\-]{1,10})", transcript)
    return match.group(1) if match else "AAPL"


def _first_accession(transcript: str) -> str | None:
    match = _ACCESSION_RE.search(transcript)
    return match.group(0) if match else None


def _first_date(transcript: str) -> str | None:
    # Tool results arrive as a JSON string nested inside the message JSON, so
    # the inner quotes are backslash-escaped by the time we see them here.
    match = re.search(r'filed_at\\?"?:\s*\\?"?(\d{4}-\d{2}-\d{2})', transcript)
    return match.group(1) if match else None
