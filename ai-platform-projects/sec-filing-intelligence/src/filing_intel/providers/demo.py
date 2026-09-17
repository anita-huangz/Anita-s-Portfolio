"""A deterministic stand-in for the model, for running the stack without a key.

Set FILING_INTEL_PROVIDER=demo and the API, the MCP server, and the eval
harness all run end to end against **real SEC EDGAR data** with no credentials.

What this is honest about: it is **extractive, not generative**. It routes tools
with a fixed policy and answers by quoting the highest-overlap passages out of
the filing it actually fetched. Every sentence it returns is text a real company
really filed -- but the selection is keyword scoring, not comprehension, so it
cannot summarise, synthesise across sources, or judge whether a question is
answerable. Those are the things the real model is for.

It exists to exercise the orchestration -- tool routing, capability enforcement,
caching, telemetry, cost accounting, the verifier gate -- and to make the UI
demonstrable by anyone who clones the repo. Token counts are plausible fixed
values so the cost arithmetic has something to work on; they measure nothing.
"""

from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

from ..contracts import ModelResponse, TokenUsage, ToolCall
from .base import ModelRequest

_ACCESSION_RE = re.compile(r"\d{10}-\d{2}-\d{6}")

#: Words too common to carry topic signal when scoring filing passages.
_STOPWORDS = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "been", "by", "do", "does", "for", "from",
    "has", "have", "how", "in", "is", "it", "its", "of", "on", "or", "our", "that", "the",
    "their", "there", "these", "this", "to", "us", "was", "we", "were", "what", "when",
    "which", "who", "will", "with", "would", "company", "companys",
})

#: Boilerplate that scores well on keyword overlap but says nothing.
_BOILERPLATE = re.compile(
    r"table of contents|see part |refer to item |incorporated by reference"
    r"|the following (discussion|risk factors)|form 10-k|annual report on form",
    re.IGNORECASE,
)


class DemoProvider:
    """Routes on the system prompt to decide which node is asking."""

    name = "demo"

    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        system = str(request.system or "")

        if system.startswith("You plan SEC-filing research"):
            return self._plan(request)
        if system.startswith("You gather evidence"):
            return self._research(request)
        if system.startswith("You turn gathered"):
            return self._analyze(request)
        return self._verify(request)

    # ------------------------------------------------------------------ #
    # Plumbing
    # ------------------------------------------------------------------ #

    @staticmethod
    def _response(text: str, in_tok: int, out_tok: int, **kw: Any) -> ModelResponse:
        return ModelResponse(
            text=text,
            model="claude-opus-5",
            provider="demo",
            usage=TokenUsage(input_tokens=in_tok, output_tokens=out_tok),
            stop_reason=kw.pop("stop_reason", "end_turn"),
            **kw,
        )

    def _tool(self, name: str, arguments: dict, call_id: str) -> ModelResponse:
        return ModelResponse(
            text="",
            tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)],
            stop_reason="tool_use",
            model="claude-opus-5",
            provider="demo",
            usage=TokenUsage(input_tokens=600, output_tokens=45),
            raw_content=[
                {"type": "tool_use", "id": call_id, "name": name, "input": arguments}
            ],
        )

    # ------------------------------------------------------------------ #
    # Nodes
    # ------------------------------------------------------------------ #

    def _plan(self, request: ModelRequest) -> ModelResponse:
        question = _question_of(request)
        steps = ["1. search_filings to find the most recent filing"]
        if _wants_financials(question):
            steps.append("2. company_financials for the reported figures")
        elif _wants_price(question):
            steps.append("2. price_reaction around the filing date")
        else:
            steps.append(f"2. fetch_filing_section for the {_section_for(question)} section")
        return self._response("\n".join(steps), 120, 40)

    def _research(self, request: ModelRequest) -> ModelResponse:
        """Fixed policy: locate the filing, then fetch only what the question needs."""
        transcript = json.dumps(request.messages, default=str)
        # Route on the question alone. Scanning the whole transcript matches
        # words inside the filing text itself -- Apple's risk factors mention
        # "revenue" and "stock" -- and fires tools the question never asked for.
        question = _question_of(request)
        ticker = _ticker(transcript)
        available = {t.name for t in request.tools}
        called = _tools_already_called(request.messages)

        if "search_filings" not in called and "search_filings" in available:
            return self._tool("search_filings", {"ticker": ticker, "limit": 3}, "tu_search")

        if (
            _wants_financials(question)
            and "company_financials" in available
            and "company_financials" not in called
        ):
            return self._tool(
                "company_financials",
                {"ticker": ticker, "concept": "Revenues", "periods": 4},
                "tu_facts",
            )

        accession = _first_accession(transcript)

        if (
            _wants_price(question)
            and "price_reaction" in available
            and "price_reaction" not in called
            and (filed := _first_date(transcript))
        ):
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
            return self._tool(
                "fetch_filing_section",
                {
                    "ticker": ticker,
                    "accession": accession,
                    "section": _section_for(question),
                    # Generous: the extractor needs real prose to choose from.
                    "max_chars": 20000,
                },
                "tu_section",
            )

        return self._response("Gathered the available evidence.", 800, 60)

    def _analyze(self, request: ModelRequest) -> ModelResponse:
        """Quote the filing rather than describe it."""
        question = _question_of(request)
        evidence = _evidence_of(request)
        accession, filed, form = _citation_from(evidence)

        if accession is None:
            return self._response(
                json.dumps(
                    {
                        "answer": "No filing was retrieved, so there is nothing to cite.",
                        "findings": [],
                    }
                ),
                1500,
                90,
            )

        passages = _rank_passages(_section_text(evidence), question, limit=4)
        facts = _financial_rows(evidence)
        reaction = _price_rows(evidence)

        quoted = [
            {
                "claim": passage,
                # Extraction is not comprehension: a quote is verbatim from the
                # filing, but nothing here judges that it answers the question.
                "confidence": "medium",
                "citations": [
                    {
                        "accession": accession,
                        "form_type": form,
                        "filed_at": filed,
                        "detail": "Quoted from the filing",
                    }
                ],
            }
            for passage in passages
        ]

        reported = [
            {
                "claim": row,
                "confidence": "high",
                "citations": [
                    {
                        "accession": accession,
                        "form_type": form,
                        "filed_at": filed,
                        "detail": "Reported figure",
                    }
                ],
            }
            for row in facts + reaction
        ]

        # A question about numbers is answered by the numbers; the quoted prose
        # is supporting colour and belongs after them.
        findings = reported + quoted if reported else quoted

        if findings:
            answer = (
                f"The {form} filed {filed} contains {len(findings)} passage"
                f"{'s' if len(findings) != 1 else ''} matching this question. "
                "Quoted verbatim below."
            )
        else:
            answer = (
                f"The {form} filed {filed} was retrieved, but no passage in the "
                "requested section matched the question closely enough to quote."
            )

        return self._response(
            json.dumps({"answer": answer, "findings": findings}), 2400, 180
        )

    def _verify(self, request: ModelRequest) -> ModelResponse:
        blob = json.dumps(request.messages, default=str)
        cited = set(_ACCESSION_RE.findall(blob))
        return self._response(
            json.dumps(
                {
                    "verified": bool(cited),
                    "note": (
                        "Every citation resolves to a filing in the gathered evidence."
                        if cited
                        else "No citations to check."
                    ),
                    "unsupported_claims": [],
                }
            ),
            1800,
            70,
        )


# --------------------------------------------------------------------------- #
# Question routing
# --------------------------------------------------------------------------- #


def _question_of(request: ModelRequest) -> str:
    """The user's question, read off the first message rather than the whole blob."""
    for message in request.messages:
        content = message.get("content")
        if isinstance(content, str):
            match = re.search(r"Question:\s*(.+)", content)
            if match:
                return match.group(1).splitlines()[0].strip().lower()
    return ""


def _wants_financials(question: str) -> bool:
    return any(
        w in question
        for w in ("revenue", "net income", "earnings", "profit", "sales", "how much")
    )


def _wants_price(question: str) -> bool:
    return any(
        w in question
        for w in ("stock react", "price react", "trading days", "share price", "stock move")
    )


def _section_for(question: str) -> str:
    # Checked most-specific first: "what does Microsoft say about AI risk" names
    # both a business phrasing and a risk topic, and risk is the real subject.
    if any(w in question for w in ("risk", "threat", "exposure", "adverse")):
        return "risk_factors"
    if any(w in question for w in ("md&a", "margin", "discussion", "liquidity")):
        return "mda"
    if any(w in question for w in ("business", "segment", "products", "what does")):
        return "business"
    return "risk_factors"


# --------------------------------------------------------------------------- #
# Evidence parsing
# --------------------------------------------------------------------------- #


def _evidence_of(request: ModelRequest) -> list[dict[str, Any]]:
    """Recover the evidence list the analyst node was handed.

    The graph serialises it into the message body and truncates at 60k, so the
    JSON can be cut mid-object; a failed parse falls back to an empty list and
    the caller degrades to "nothing to quote" rather than raising.
    """
    for message in request.messages:
        content = message.get("content")
        if not isinstance(content, str) or "Evidence gathered:" not in content:
            continue
        blob = content.split("Evidence gathered:", 1)[1].strip()
        try:
            parsed = json.loads(blob)
        except (json.JSONDecodeError, ValueError):
            return []
        return parsed if isinstance(parsed, list) else []
    return []


def _results(evidence: list[dict[str, Any]], tool: str) -> list[Any]:
    return [
        item.get("data")
        for item in evidence
        if item.get("kind") == "tool_result" and item.get("tool") == tool and item.get("ok")
    ]


def _citation_from(evidence: list[dict[str, Any]]) -> tuple[str | None, str, str]:
    for filings in _results(evidence, "search_filings"):
        if isinstance(filings, list) and filings:
            first = filings[0]
            return (
                first.get("accession"),
                first.get("filed_at", "unknown"),
                first.get("form_type", "10-K"),
            )
    return None, "unknown", "10-K"


def _section_text(evidence: list[dict[str, Any]]) -> str:
    for section in _results(evidence, "fetch_filing_section"):
        if isinstance(section, dict) and section.get("text"):
            return str(section["text"])
    return ""


def _financial_rows(evidence: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for facts in _results(evidence, "company_financials"):
        if not isinstance(facts, list):
            continue
        for fact in facts[:4]:
            value = fact.get("value")
            if value is None:
                continue
            span = _span_label(fact.get("period_start"), fact.get("period_end"))
            rows.append(
                f"{fact.get('concept')} ({span} ending {fact.get('period_end')}): "
                f"{_money(float(value))} {fact.get('unit')}, "
                f"as reported on {fact.get('form_type')}."
            )
    return rows


def _price_rows(evidence: list[dict[str, Any]]) -> list[str]:
    rows: list[str] = []
    for reaction in _results(evidence, "price_reaction"):
        if not isinstance(reaction, dict):
            continue
        windows = reaction.get("windows") or {}
        moves = ", ".join(f"{h}: {v * 100:+.2f}%" for h, v in sorted(windows.items()))
        if moves:
            rows.append(
                f"Price reaction after {reaction.get('event_date')} "
                f"(baseline close ${reaction.get('baseline_close'):.2f}): {moves}."
            )
    return rows


def _span_label(start: Any, end: Any) -> str:
    """Name the period a figure covers, so a quarter is not read as a year."""
    if not start or not end:
        return "as of"
    try:
        days = (date.fromisoformat(str(end)) - date.fromisoformat(str(start))).days
    except ValueError:
        return "period"
    if days >= 300:
        return "fiscal year"
    if days >= 150:
        return "half year"
    return "quarter"


def _money(value: float) -> str:
    for cutoff, suffix in ((1e12, "T"), (1e9, "B"), (1e6, "M")):
        if abs(value) >= cutoff:
            return f"${value / cutoff:.2f}{suffix}"
    return f"${value:,.0f}"


# --------------------------------------------------------------------------- #
# Passage ranking
# --------------------------------------------------------------------------- #


def _keywords(question: str) -> set[str]:
    words = re.findall(r"[a-z]{3,}", question.lower())
    return {w for w in words if w not in _STOPWORDS}


def _sentences(text: str) -> list[str]:
    """Split filing prose into quotable sentences."""
    cleaned = re.sub(r"\s+", " ", text)
    parts = re.split(r"(?<=[.;])\s+(?=[A-Z(])", cleaned)
    return [
        p.strip()
        for p in parts
        # Long enough to stand alone, short enough to read in a card.
        if 80 <= len(p.strip()) <= 420 and not _BOILERPLATE.search(p)
    ]


def _rank_passages(text: str, question: str, limit: int = 4) -> list[str]:
    """Highest keyword-overlap sentences, de-duplicated, in document order.

    Document order rather than score order: consecutive risk-factor sentences
    read as an argument, and shuffling them into score order breaks it.
    """
    if not text:
        return []

    keywords = _keywords(question)
    if not keywords:
        return _sentences(text)[:limit]

    scored: list[tuple[int, int, str]] = []
    for position, sentence in enumerate(_sentences(text)):
        tokens = set(re.findall(r"[a-z]{3,}", sentence.lower()))
        overlap = len(keywords & tokens)
        if overlap:
            scored.append((overlap, position, sentence))

    scored.sort(key=lambda row: (-row[0], row[1]))

    chosen: list[tuple[int, str]] = []
    seen: set[str] = set()
    for _, position, sentence in scored:
        fingerprint = sentence[:60].lower()
        if fingerprint in seen:
            continue
        seen.add(fingerprint)
        chosen.append((position, sentence))
        if len(chosen) == limit:
            break

    return [sentence for _, sentence in sorted(chosen)]


# --------------------------------------------------------------------------- #
# Transcript helpers
# --------------------------------------------------------------------------- #


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
