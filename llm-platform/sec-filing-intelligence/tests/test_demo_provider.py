"""The demo provider: the path anyone without an API key actually runs.

`FILING_INTEL_PROVIDER=demo` is what a reader who clones the repo gets, so its
routing policy is production code for that reader even though no model is
involved. These tests pin the policy -- which node is asked, which tool fires,
what gets quoted -- and the honesty boundaries the module's docstring claims:
it never invents a citation, and it degrades rather than raises when the
evidence it is handed is truncated.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from filing_intel.config import Settings
from filing_intel.errors import ConfigError
from filing_intel.providers import ModelRequest, ToolSpec
from filing_intel.providers.demo import (
    DemoProvider,
    _first_date,
    _money,
    _rank_passages,
    _section_for,
    _span_label,
    _ticker,
)
from filing_intel.providers.registry import _require_region, build_provider

PLAN = "You plan SEC-filing research"
RESEARCH = "You gather evidence"
ANALYZE = "You turn gathered"
VERIFY = "You check that every claim"

ACCESSION = "0000320193-23-000106"

ALL_TOOLS = ["search_filings", "fetch_filing_section", "company_financials", "price_reaction"]


def spec(name: str) -> ToolSpec:
    return ToolSpec(name=name, description=name, input_schema={"type": "object"})


def request(
    system: str,
    question: str = "what are the supply chain risks",
    *,
    ticker: str = "AAPL",
    tools: list[str] | None = None,
    extra: list[dict[str, Any]] | None = None,
) -> ModelRequest:
    messages: list[dict[str, Any]] = [
        {"role": "user", "content": f"Company: {ticker}\nQuestion: {question}"}
    ]
    messages.extend(extra or [])
    return ModelRequest(
        model="claude-opus-5",
        messages=messages,
        system=system,
        tools=[spec(n) for n in (ALL_TOOLS if tools is None else tools)],
    )


def called(name: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """An assistant turn showing `name` was already invoked."""
    return {
        "role": "assistant",
        "content": [{"type": "tool_use", "id": f"tu_{name}", "name": name, "input": payload or {}}],
    }


def result(tool: str, data: Any, ok: bool = True) -> dict[str, Any]:
    return {"kind": "tool_result", "tool": tool, "ok": ok, "data": data}


def evidence_turn(items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"role": "user", "content": "Evidence gathered: " + json.dumps(items)}


SEARCH_RESULT = [
    {"accession": ACCESSION, "filed_at": "2023-11-03", "form_type": "10-K", "ticker": "AAPL"}
]


async def complete(request_: ModelRequest) -> Any:
    return await DemoProvider().complete(request_)


# --------------------------------------------------------------------------- #
# Node routing
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("system", "marker"),
    [
        (PLAN, "search_filings to find"),
        (ANALYZE, '"answer"'),
        (VERIFY, '"verified"'),
    ],
)
async def test_the_system_prompt_decides_which_node_is_answering(system, marker):
    response = await complete(request(system))
    assert marker in response.text


async def test_an_unrecognised_system_prompt_falls_through_to_the_verifier():
    # The graph only has four nodes, so "not one of the other three" is the
    # verifier rather than an error -- but that default should be deliberate.
    response = await complete(request("You are something else entirely"))
    assert "verified" in json.loads(response.text)


async def test_every_response_is_attributed_to_the_demo_provider():
    response = await complete(request(PLAN))
    assert response.provider == "demo"
    assert response.usage.input_tokens > 0


async def test_calls_are_counted():
    provider = DemoProvider()
    for _ in range(3):
        await provider.complete(request(PLAN))
    assert provider.calls == 3


# --------------------------------------------------------------------------- #
# Planning
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("what was revenue last year", "company_financials"),
        ("how did the stock react over the following trading days", "price_reaction"),
        ("what are the supply chain risks", "fetch_filing_section for the risk_factors"),
        ("describe the business segments", "fetch_filing_section for the business"),
    ],
)
async def test_the_plan_names_the_tool_the_question_needs(question, expected):
    response = await complete(request(PLAN, question))
    assert response.text.startswith("1. search_filings")
    assert expected in response.text


async def test_a_price_question_phrased_around_earnings_plans_financials_instead():
    # Documented limitation, not an accident: the financial keywords are checked
    # first, and "earnings" is one of them. A reader asking how the stock moved
    # after earnings gets the reported figures, not the price reaction. Keyword
    # routing cannot tell which noun is the subject -- that is what the real
    # model is for.
    response = await complete(request(PLAN, "how did the stock react to the earnings"))
    assert "company_financials" in response.text
    assert "price_reaction" not in response.text


# --------------------------------------------------------------------------- #
# Research: tool routing
# --------------------------------------------------------------------------- #


async def test_the_filing_is_located_before_anything_else_is_fetched():
    response = await complete(request(RESEARCH, "what was revenue last year"))
    assert [c.name for c in response.tool_calls] == ["search_filings"]
    assert response.tool_calls[0].arguments["ticker"] == "AAPL"


async def test_the_ticker_is_read_off_the_question_not_hardcoded():
    response = await complete(request(RESEARCH, ticker="MSFT"))
    assert response.tool_calls[0].arguments["ticker"] == "MSFT"


async def test_a_financial_question_fetches_facts_once_the_filing_is_known():
    response = await complete(
        request(
            RESEARCH,
            "what was revenue last year",
            extra=[
                called("search_filings"),
                evidence_turn([result("search_filings", SEARCH_RESULT)]),
            ],
        )
    )
    call = response.tool_calls[0]
    assert call.name == "company_financials"
    assert call.arguments["concept"] == "Revenues"


async def test_a_price_question_needs_a_filing_date_to_anchor_the_event():
    history = [
        called("search_filings"),
        {"role": "user", "content": json.dumps([result("search_filings", SEARCH_RESULT)])},
    ]
    response = await complete(
        request(RESEARCH, "how did the stock react over the following trading days", extra=history)
    )
    call = response.tool_calls[0]
    assert call.name == "price_reaction"
    assert call.arguments["event_date"] == "2023-11-03"


async def test_without_a_filing_date_the_price_branch_falls_through_to_the_section():
    # No filed_at anywhere, so there is no event to measure around. Falling back
    # to the section beats calling price_reaction with a guessed date.
    history = [
        called("search_filings"),
        {"role": "user", "content": json.dumps([{"accession": ACCESSION}])},
    ]
    response = await complete(
        request(RESEARCH, "how did the stock react over the following trading days", extra=history)
    )
    assert response.tool_calls[0].name == "fetch_filing_section"


async def test_a_prose_question_fetches_the_section_the_question_is_about():
    history = [
        called("search_filings"),
        {"role": "user", "content": json.dumps([result("search_filings", SEARCH_RESULT)])},
    ]
    response = await complete(request(RESEARCH, "what are the supply chain risks", extra=history))
    call = response.tool_calls[0]
    assert call.name == "fetch_filing_section"
    assert call.arguments["section"] == "risk_factors"
    assert call.arguments["accession"] == ACCESSION


async def test_a_tool_the_session_may_not_use_is_never_called():
    # Capability enforcement lives above the provider, but a provider that asks
    # for a forbidden tool turns every restricted session into an error. The
    # policy only ever names tools it was handed.
    response = await complete(
        request(RESEARCH, "what was revenue last year", tools=["search_filings"])
    )
    assert response.tool_calls[0].name == "search_filings"

    history = [called("search_filings"), evidence_turn([result("search_filings", SEARCH_RESULT)])]
    response = await complete(
        request(RESEARCH, "what was revenue last year", tools=["search_filings"], extra=history)
    )
    assert response.tool_calls == []
    assert "Gathered the available evidence" in response.text


async def test_no_tool_is_called_twice():
    history = [
        called("search_filings"),
        called("fetch_filing_section"),
        evidence_turn([result("search_filings", SEARCH_RESULT)]),
    ]
    response = await complete(request(RESEARCH, extra=history))
    assert response.tool_calls == []


# --------------------------------------------------------------------------- #
# Analysis: what gets quoted, and what never gets invented
# --------------------------------------------------------------------------- #

RISK_TEXT = (
    "The Company depends on supply chain partners concentrated in a small number of "
    "regions, and a disruption there would materially affect product availability. "
    "Table of contents and other navigational material appears throughout the filing. "
    "Component shortages in the supply chain have previously delayed shipments of new "
    "products and could do so again in future periods without advance warning. "
    "The Company also faces competition from firms with greater financial resources "
    "than it has available for research and development in every market it serves."
)


async def test_with_no_filing_retrieved_nothing_is_cited():
    response = await complete(request(ANALYZE, extra=[evidence_turn([])]))
    payload = json.loads(response.text)
    assert payload["findings"] == []
    assert "nothing to cite" in payload["answer"]


async def test_quoted_passages_carry_the_accession_they_came_from():
    items = [
        result("search_filings", SEARCH_RESULT),
        result("fetch_filing_section", {"text": RISK_TEXT}),
    ]
    response = await complete(
        request(ANALYZE, "what are the supply chain risks", extra=[evidence_turn(items)])
    )
    payload = json.loads(response.text)
    assert payload["findings"]
    for finding in payload["findings"]:
        assert finding["claim"] in RISK_TEXT.replace("  ", " ")
        assert finding["citations"][0]["accession"] == ACCESSION
        assert finding["citations"][0]["filed_at"] == "2023-11-03"


async def test_extraction_never_claims_more_than_medium_confidence_in_a_quote():
    items = [
        result("search_filings", SEARCH_RESULT),
        result("fetch_filing_section", {"text": RISK_TEXT}),
    ]
    response = await complete(
        request(ANALYZE, "what are the supply chain risks", extra=[evidence_turn(items)])
    )
    payload = json.loads(response.text)
    assert {f["confidence"] for f in payload["findings"]} == {"medium"}


async def test_reported_figures_are_high_confidence_and_come_before_the_prose():
    items = [
        result("search_filings", SEARCH_RESULT),
        result("fetch_filing_section", {"text": RISK_TEXT}),
        result(
            "company_financials",
            [
                {
                    "concept": "Revenues",
                    "unit": "USD",
                    "value": 383_285_000_000.0,
                    "period_start": "2022-10-01",
                    "period_end": "2023-09-30",
                    "form_type": "10-K",
                }
            ],
        ),
    ]
    response = await complete(
        request(
            ANALYZE,
            "what were revenues and the supply chain risks",
            extra=[evidence_turn(items)],
        )
    )
    findings = json.loads(response.text)["findings"]
    assert findings[0]["confidence"] == "high"
    assert "$383.29B" in findings[0]["claim"]
    assert "fiscal year" in findings[0]["claim"]
    assert findings[-1]["confidence"] == "medium"


async def test_a_figure_with_no_value_is_dropped_rather_than_reported_as_null():
    items = [
        result("search_filings", SEARCH_RESULT),
        result("company_financials", [{"concept": "Revenues", "value": None, "unit": "USD"}]),
    ]
    response = await complete(request(ANALYZE, "what was revenue", extra=[evidence_turn(items)]))
    payload = json.loads(response.text)
    assert payload["findings"] == []
    assert "no passage" in payload["answer"]


async def test_price_windows_are_rendered_as_signed_percentages():
    items = [
        result("search_filings", SEARCH_RESULT),
        result(
            "price_reaction",
            {
                "event_date": "2023-11-03",
                "baseline_close": 170.0,
                "windows": {"1d": 0.0123, "5d": -0.02},
            },
        ),
    ]
    response = await complete(
        request(ANALYZE, "how did the stock move", extra=[evidence_turn(items)])
    )
    claim = json.loads(response.text)["findings"][0]["claim"]
    assert "1d: +1.23%" in claim
    assert "5d: -2.00%" in claim
    assert "$170.00" in claim


async def test_a_failed_tool_result_contributes_no_evidence():
    items = [result("search_filings", SEARCH_RESULT, ok=False)]
    response = await complete(request(ANALYZE, extra=[evidence_turn(items)]))
    assert "nothing to cite" in json.loads(response.text)["answer"]


async def test_evidence_truncated_mid_object_degrades_instead_of_raising():
    # The graph truncates the serialised evidence at 60k, so the JSON the
    # analyst sees can be cut mid-object. That must not take the run down.
    blob = json.dumps([result("search_filings", SEARCH_RESULT)])[:-12]
    response = await complete(
        request(ANALYZE, extra=[{"role": "user", "content": "Evidence gathered: " + blob}])
    )
    assert "nothing to cite" in json.loads(response.text)["answer"]


async def test_evidence_that_parses_to_the_wrong_shape_is_ignored():
    response = await complete(
        request(
            ANALYZE,
            extra=[{"role": "user", "content": 'Evidence gathered: {"not": "a list"}'}],
        )
    )
    assert "nothing to cite" in json.loads(response.text)["answer"]


# --------------------------------------------------------------------------- #
# Verification
# --------------------------------------------------------------------------- #


async def test_the_verifier_passes_only_when_an_accession_is_actually_present():
    with_citation = await complete(
        request(VERIFY, extra=[{"role": "user", "content": f"cited {ACCESSION}"}])
    )
    assert json.loads(with_citation.text)["verified"] is True

    without = await complete(request(VERIFY))
    payload = json.loads(without.text)
    assert payload["verified"] is False
    assert payload["unsupported_claims"] == []


# --------------------------------------------------------------------------- #
# Passage ranking
# --------------------------------------------------------------------------- #


def test_no_text_means_no_passages():
    assert _rank_passages("", "supply chain") == []


def test_passages_are_returned_in_document_order_not_score_order():
    # Consecutive risk-factor sentences read as an argument; score order breaks it.
    first = (
        "Supply chain disruption in any single region would materially affect the "
        "Company's ability to deliver products on the schedule it has announced. "
    )
    second = (
        "Separately, foreign exchange risk reduces reported results whenever the "
        "dollar strengthens against the currencies in which sales are denominated. "
    )
    third = (
        "Concentration of supply chain manufacturing capacity in a small number of "
        "partners remains a supply risk the Company monitors closely each quarter."
    )
    # Scores are 3, 3, 1 -- so score order would put the middle sentence last.
    ranked = _rank_passages(first + second + third, "supply chain risk", limit=3)
    assert ranked == [p.strip() for p in (first, second, third)]


def test_a_question_with_only_stopwords_falls_back_to_the_opening_passages():
    text = (
        "The first sentence of the section runs long enough to be quotable on its "
        "own and introduces the subject matter that follows it below. "
        "The second sentence continues the same discussion at a comparable length "
        "so that it also clears the minimum quotable size for this test."
    )
    assert len(_rank_passages(text, "what is the of and to", limit=1)) == 1


def test_boilerplate_is_not_quotable_even_when_it_matches_the_question():
    text = (
        "Table of contents references to the supply chain discussion appear in the "
        "navigation and repeat the phrase without saying anything about it at all."
    )
    assert _rank_passages(text, "supply chain") == []


def test_fragments_and_wall_of_text_are_both_skipped():
    short = "Supply chain risk. "
    long = "Supply chain " + "exposure " * 200
    assert _rank_passages(short + long, "supply chain") == []


def test_near_duplicate_passages_are_collapsed():
    stem = (
        "The Company depends on supply chain partners concentrated in a small number "
        "of regions, which creates risk"
    )
    text = f"{stem} in the current fiscal year. {stem} in the following fiscal year."
    assert len(_rank_passages(text, "supply chain risk")) == 1


# --------------------------------------------------------------------------- #
# Formatting helpers
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (1.5e12, "$1.50T"),
        (383_285_000_000.0, "$383.29B"),
        (2_500_000.0, "$2.50M"),
        (12_345.0, "$12,345"),
        (-4.2e9, "$-4.20B"),
    ],
)
def test_money_picks_the_unit_that_keeps_the_figure_readable(value, expected):
    assert _money(value) == expected


@pytest.mark.parametrize(
    ("start", "end", "expected"),
    [
        ("2022-10-01", "2023-09-30", "fiscal year"),
        ("2023-04-01", "2023-09-30", "half year"),
        ("2023-07-01", "2023-09-30", "quarter"),
        (None, "2023-09-30", "as of"),
        ("not-a-date", "2023-09-30", "period"),
    ],
)
def test_a_quarter_is_never_labelled_as_a_year(start, end, expected):
    assert _span_label(start, end) == expected


@pytest.mark.parametrize(
    ("question", "section"),
    [
        ("what does the company say about ai risk", "risk_factors"),
        ("what does the company do", "business"),
        ("discuss gross margin trends", "mda"),
        ("something with no keywords at all", "risk_factors"),
    ],
)
def test_risk_wins_over_business_phrasing(question, section):
    assert _section_for(question) == section


def test_an_unknown_company_line_falls_back_to_a_working_ticker():
    assert _ticker("no company here") == "AAPL"
    assert _ticker("Company: BRK.B and more") == "BRK.B"


def test_the_filing_date_is_found_through_json_escaping():
    # Tool results arrive as a JSON string nested inside the message JSON, so
    # the inner quotes are backslash-escaped by the time the provider sees them.
    assert _first_date(json.dumps(json.dumps({"filed_at": "2023-11-03"}))) == "2023-11-03"
    assert _first_date('"filed_at": "2024-02-01"') == "2024-02-01"
    assert _first_date("no dates here") is None


# --------------------------------------------------------------------------- #
# Provider selection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("provider", "expected"),
    [("anthropic", "anthropic"), ("demo", "demo"), ("replay", "replay")],
)
def test_the_configured_provider_is_the_one_that_gets_built(provider, expected):
    assert build_provider(Settings(provider=provider)).name == expected


def test_bedrock_refuses_to_start_without_a_region(monkeypatch):
    monkeypatch.delenv("AWS_REGION", raising=False)
    with pytest.raises(ConfigError, match="AWS_REGION"):
        build_provider(Settings(provider="bedrock"))


def test_bedrock_uses_the_region_from_the_environment(monkeypatch):
    # Asserted on the resolver rather than the provider: building the provider
    # constructs a live Bedrock client, which is exactly what CI must not do.
    monkeypatch.setenv("AWS_REGION", "us-west-2")
    assert _require_region(Settings(provider="bedrock")) == "us-west-2"


def test_recording_mode_gives_the_replay_provider_something_to_record_with():
    plain = build_provider(Settings(provider="replay", replay_record=False))
    recording = build_provider(Settings(provider="replay", replay_record=True))
    assert plain._record_with is None
    assert recording._record_with is not None


def test_an_unknown_provider_names_itself_in_the_error():
    settings = Settings(provider="replay")
    object.__setattr__(settings, "provider", "wat")
    with pytest.raises(ConfigError, match="wat"):
        build_provider(settings)
