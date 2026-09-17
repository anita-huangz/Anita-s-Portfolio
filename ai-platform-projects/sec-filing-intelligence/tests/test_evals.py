"""The eval harness itself must be trustworthy before its numbers mean anything."""

from __future__ import annotations

import json

from evals.harness import EvalCase, EvalReport, RunResult, grade, load_dataset, run_eval

from conftest import text_response
from filing_intel.contracts import Citation, Finding, ResearchResponse
from filing_intel.providers import ScriptedProvider
from filing_intel.runtime import FilingIntelRuntime

ANALYST_JSON = json.dumps(
    {
        "answer": "Apple flags supply-chain concentration as a principal risk.",
        "findings": [
            {
                "claim": "Concentrated manufacturing partners.",
                "confidence": "high",
                "citations": [
                    {
                        "accession": "0000320193-23-000106",
                        "form_type": "10-K",
                        "filed_at": "2023-11-03",
                        "detail": "Item 1A",
                    }
                ],
            }
        ],
    }
)
VERIFIER_JSON = json.dumps({"verified": True, "note": "ok", "unsupported_claims": []})


def response(**kw) -> ResearchResponse:
    base = {
        "ticker": "AAPL",
        "question": "q",
        "answer": "Apple depends on a concentrated supply chain.",
        "findings": [
            Finding(
                claim="c",
                confidence="high",
                citations=[
                    Citation(
                        accession="0000320193-23-000106",
                        form_type="10-K",
                        filed_at="2023-11-03",
                        detail="Item 1A",
                    )
                ],
            )
        ],
        "session_id": "s",
        "trace_id": "t",
        "verified": True,
    }
    return ResearchResponse(**{**base, **kw})


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #


def test_expected_tool_that_ran_passes():
    case = EvalCase("c", "AAPL", "A question?", expect_tools=("search_filings",))
    checks = grade(case, response(), ["search_filings"])
    assert all(c.passed for c in checks)


def test_expected_tool_that_never_ran_fails_with_a_reason():
    case = EvalCase("c", "AAPL", "A question?", expect_tools=("price_reaction",))
    failed = [c for c in grade(case, response(), ["search_filings"]) if not c.passed]
    assert failed[0].name == "tool:price_reaction"
    assert "never called" in failed[0].detail


def test_answer_substring_match_is_case_insensitive():
    case = EvalCase("c", "AAPL", "A question?", expect_answer_contains=("CONCENTRATED",))
    assert all(c.passed for c in grade(case, response(), []))


def test_missing_substring_fails():
    case = EvalCase("c", "AAPL", "A question?", expect_answer_contains=("dividend",))
    assert any(not c.passed for c in grade(case, response(), []))


def test_uncited_finding_fails_the_citation_check():
    uncited = response(findings=[Finding(claim="c", confidence="low", citations=[])])
    failed = [c for c in grade(EvalCase("c", "AAPL", "A question?"), uncited, []) if not c.passed]
    assert failed[0].name == "citations_present"
    assert "no citation" in failed[0].detail


def test_zero_findings_fails_the_citation_check():
    checks = grade(EvalCase("c", "AAPL", "A question?"), response(findings=[]), [])
    failed = [c for c in checks if not c.passed]
    assert "no findings" in failed[0].detail


def test_verification_check_is_opt_in():
    unverified = response(verified=False, verifier_note="citation not found")
    assert all(c.passed for c in grade(EvalCase("c", "AAPL", "A question?"), unverified, []))

    strict = EvalCase("c", "AAPL", "A question?", require_verified=True)
    failed = [c for c in grade(strict, unverified, []) if not c.passed]
    assert failed[0].name == "verified"


def test_a_case_with_no_expectations_still_checks_for_an_answer():
    case = EvalCase("c", "AAPL", "A question?", require_citations=False)
    assert grade(case, response(), [])[0].name == "answered"
    assert not grade(case, response(answer="  "), [])[0].passed


# --------------------------------------------------------------------------- #
# Report arithmetic
# --------------------------------------------------------------------------- #


def run(case_id="c", passed=True, latency=100.0, cost=0.01, error=None, sig=(True,)):
    from evals.harness import CheckResult

    return RunResult(
        case_id=case_id,
        attempt=0,
        passed=passed,
        checks=[CheckResult(f"chk{i}", v) for i, v in enumerate(sig)],
        latency_ms=latency,
        cost_usd=cost,
        tool_calls=1,
        error=error,
    )


def test_empty_report_does_not_divide_by_zero():
    report = EvalReport()
    assert (report.accuracy, report.consistency, report.reliability) == (0.0, 0.0, 0.0)
    assert report.p50_latency_ms == 0.0


def test_accuracy_and_reliability_are_distinct():
    """A run can complete cleanly and still fail its checks."""
    report = EvalReport(cases=1, total_runs=4, passed_runs=2, error_runs=1)
    assert report.accuracy == 0.5
    assert report.reliability == 0.75


def test_latency_percentiles():
    report = EvalReport(latencies_ms=[10.0, 20.0, 30.0, 40.0, 1000.0])
    assert report.p50_latency_ms == 30.0
    assert report.p95_latency_ms == 1000.0


def test_render_does_not_crash_on_an_empty_report():
    assert "0 runs" in EvalReport().render()


# --------------------------------------------------------------------------- #
# End-to-end over the real runtime
# --------------------------------------------------------------------------- #


def script(n: int):
    return [
        text_response("plan"),
        text_response("done"),
        text_response(ANALYST_JSON),
        text_response(VERIFIER_JSON),
    ] * n


async def test_repeated_runs_of_a_deterministic_workflow_are_fully_consistent(
    settings, edgar, prices, cache, telemetry
):
    runtime = FilingIntelRuntime(
        settings, ScriptedProvider(script(9)), cache, edgar, prices, telemetry
    )
    cases = [EvalCase("aapl-risk", "AAPL", "What are the supply chain risks?")]

    report, results = await run_eval(runtime, cases, repeats=3, concurrency=1)

    assert report.total_runs == 3
    assert report.accuracy == 1.0
    assert report.consistency == 1.0
    assert report.reliability == 1.0
    assert report.total_cost_usd > 0
    assert all(r.passed for r in results)


async def test_inconsistent_grading_across_repeats_is_detected(
    settings, edgar, prices, cache, telemetry
):
    """The consistency metric must actually catch a flapping workflow."""
    good = [text_response("plan"), text_response("done"), text_response(ANALYST_JSON),
            text_response(VERIFIER_JSON)]
    bad = [text_response("plan"), text_response("done"),
           text_response(json.dumps({"answer": "no idea", "findings": []})),
           text_response(VERIFIER_JSON)]
    runtime = FilingIntelRuntime(
        settings, ScriptedProvider(good + bad), cache, edgar, prices, telemetry
    )
    report, _ = await run_eval(
        runtime, [EvalCase("flaky", "AAPL", "Is it flaky?")], repeats=2, concurrency=1
    )
    assert report.accuracy == 0.5
    assert report.consistency == 0.0
    assert report.check_failures["citations_present"] == 1


async def test_a_raising_run_is_counted_as_unreliable_not_as_a_crash(
    settings, edgar, prices, cache, telemetry
):
    class Exploding:
        name = "boom"

        async def complete(self, request):
            raise RuntimeError("provider exploded")

    runtime = FilingIntelRuntime(settings, Exploding(), cache, edgar, prices, telemetry)
    report, results = await run_eval(runtime, [EvalCase("c", "AAPL", "A question?")], repeats=2)

    # The graph catches provider errors, so these complete but fail grading.
    assert report.total_runs == 2
    assert report.accuracy == 0.0
    assert all(not r.passed for r in results)


async def test_multiple_cases_run_concurrently_and_are_reported_per_case(
    settings, edgar, prices, cache, telemetry
):
    runtime = FilingIntelRuntime(
        settings, ScriptedProvider(script(12)), cache, edgar, prices, telemetry
    )
    cases = [
        EvalCase("a", "AAPL", "Question A?"),
        EvalCase("b", "AAPL", "Question B?"),
        EvalCase("c", "AAPL", "Question C?"),
    ]
    report, _ = await run_eval(runtime, cases, repeats=2, concurrency=3)
    assert report.total_runs == 6
    assert set(report.per_case_pass_rate) == {"a", "b", "c"}


# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #


def test_shipped_dataset_loads_and_is_well_formed():
    cases = load_dataset("evals/dataset.jsonl")
    assert len(cases) >= 5
    assert len({c.case_id for c in cases}) == len(cases)  # ids unique
    for case in cases:
        assert case.ticker.isupper()
        assert case.question.endswith("?")


def test_dataset_covers_every_tool():
    covered = {
        tool
        for case in load_dataset("evals/dataset.jsonl")
        for tool in case.expect_tools
    }
    assert covered == {
        "search_filings", "fetch_filing_section", "company_financials", "price_reaction"
    }
