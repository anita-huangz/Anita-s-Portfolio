"""Automated evaluation harness.

Runs a dataset of research questions through the platform N times each and
measures the things that actually matter for a workflow whose output feeds a
decision:

  accuracy    -- did the graded checks pass?
  consistency -- did repeated runs of the same case reach the same verdict?
  reliability -- what fraction completed without a failure being recorded?
  latency     -- p50 / p95 wall clock
  cost        -- estimated spend per case and in total
  failures    -- grouped by kind, so a regression names its own cause

Repetition is the point of the `repeats` parameter: a single pass tells you
whether the workflow can succeed, not whether it does so dependably.

Usage:
    python -m evals.harness --dataset evals/dataset.jsonl --repeats 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from filing_intel.config import Settings, get_settings
from filing_intel.contracts import ResearchRequest, ResearchResponse
from filing_intel.runtime import FilingIntelRuntime
from filing_intel.telemetry import percentile

# --------------------------------------------------------------------------- #
# Dataset
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class EvalCase:
    case_id: str
    ticker: str
    question: str
    #: Tools the run must have invoked, by name.
    expect_tools: tuple[str, ...] = ()
    #: Case-insensitive substrings the answer must contain.
    expect_answer_contains: tuple[str, ...] = ()
    #: Require at least one finding, each carrying at least one citation.
    require_citations: bool = True
    #: Require the verifier to have passed the answer.
    require_verified: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> EvalCase:
        return cls(
            case_id=raw["case_id"],
            ticker=raw["ticker"],
            question=raw["question"],
            expect_tools=tuple(raw.get("expect_tools", [])),
            expect_answer_contains=tuple(raw.get("expect_answer_contains", [])),
            require_citations=raw.get("require_citations", True),
            require_verified=raw.get("require_verified", False),
        )


def load_dataset(path: str | Path) -> list[EvalCase]:
    cases = []
    for line in Path(path).read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            cases.append(EvalCase.from_dict(json.loads(line)))
    return cases


# --------------------------------------------------------------------------- #
# Grading
# --------------------------------------------------------------------------- #


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str = ""


@dataclass
class RunResult:
    case_id: str
    attempt: int
    passed: bool
    checks: list[CheckResult]
    latency_ms: float
    cost_usd: float
    tool_calls: int
    error: str | None = None

    @property
    def signature(self) -> tuple[bool, ...]:
        """What consistency is measured over: the per-check verdict vector."""
        return tuple(c.passed for c in self.checks)


def grade(case: EvalCase, response: ResearchResponse, tools_used: list[str]) -> list[CheckResult]:
    checks: list[CheckResult] = []

    for tool in case.expect_tools:
        used = tool in tools_used
        checks.append(
            CheckResult(f"tool:{tool}", used, "" if used else f"{tool} was never called")
        )

    answer = (response.answer or "").lower()
    for needle in case.expect_answer_contains:
        found = needle.lower() in answer
        checks.append(
            CheckResult(
                f"answer_contains:{needle}", found, "" if found else f"missing {needle!r}"
            )
        )

    if case.require_citations:
        has_findings = bool(response.findings)
        all_cited = has_findings and all(f.citations for f in response.findings)
        checks.append(
            CheckResult(
                "citations_present",
                all_cited,
                ""
                if all_cited
                else ("no findings produced" if not has_findings else "a finding had no citation"),
            )
        )

    if case.require_verified:
        checks.append(
            CheckResult(
                "verified",
                response.verified,
                "" if response.verified else (response.verifier_note or "not verified"),
            )
        )

    if not checks:
        checks.append(CheckResult("answered", bool(response.answer.strip())))

    return checks


# --------------------------------------------------------------------------- #
# Report
# --------------------------------------------------------------------------- #


@dataclass
class EvalReport:
    total_runs: int = 0
    passed_runs: int = 0
    error_runs: int = 0
    cases: int = 0
    fully_consistent_cases: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    total_cost_usd: float = 0.0
    check_failures: Counter = field(default_factory=Counter)
    errors_by_kind: Counter = field(default_factory=Counter)
    per_case_pass_rate: dict[str, float] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return self.passed_runs / self.total_runs if self.total_runs else 0.0

    @property
    def reliability(self) -> float:
        """Fraction of runs that completed without raising."""
        if not self.total_runs:
            return 0.0
        return (self.total_runs - self.error_runs) / self.total_runs

    @property
    def consistency(self) -> float:
        """Fraction of cases whose repeats all graded identically."""
        return self.fully_consistent_cases / self.cases if self.cases else 0.0

    @property
    def p50_latency_ms(self) -> float:
        # Same nearest-rank definition the live telemetry uses, so an eval
        # number and a production number mean the same thing.
        return percentile(self.latencies_ms, 0.50)

    @property
    def p95_latency_ms(self) -> float:
        return percentile(self.latencies_ms, 0.95)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_runs": self.total_runs,
            "cases": self.cases,
            "accuracy": round(self.accuracy, 4),
            "consistency": round(self.consistency, 4),
            "reliability": round(self.reliability, 4),
            "p50_latency_ms": round(self.p50_latency_ms, 1),
            "p95_latency_ms": round(self.p95_latency_ms, 1),
            "total_cost_usd": round(self.total_cost_usd, 6),
            "cost_per_run_usd": round(
                self.total_cost_usd / self.total_runs if self.total_runs else 0.0, 6
            ),
            "top_check_failures": dict(self.check_failures.most_common(10)),
            "errors_by_kind": dict(self.errors_by_kind),
            "per_case_pass_rate": {k: round(v, 3) for k, v in self.per_case_pass_rate.items()},
        }

    def render(self) -> str:
        d = self.to_dict()
        lines = [
            "=" * 62,
            f"  {self.total_runs} runs over {self.cases} cases",
            "=" * 62,
            f"  accuracy     {d['accuracy']:>8.1%}   (graded checks passed)",
            f"  consistency  {d['consistency']:>8.1%}   (repeats agreed)",
            f"  reliability  {d['reliability']:>8.1%}   (completed without error)",
            f"  latency      p50 {d['p50_latency_ms']:.0f}ms / p95 {d['p95_latency_ms']:.0f}ms",
            f"  cost         ${d['total_cost_usd']:.4f} total, "
            f"${d['cost_per_run_usd']:.5f}/run",
        ]
        if d["top_check_failures"]:
            lines.append("-" * 62)
            lines.append("  failing checks:")
            for name, count in d["top_check_failures"].items():
                lines.append(f"    {count:>4}x  {name}")
        if d["errors_by_kind"]:
            lines.append("-" * 62)
            lines.append("  errors:")
            for kind, count in d["errors_by_kind"].items():
                lines.append(f"    {count:>4}x  {kind}")
        weak = {k: v for k, v in d["per_case_pass_rate"].items() if v < 1.0}
        if weak:
            lines.append("-" * 62)
            lines.append("  cases below 100%:")
            for case_id, rate in sorted(weak.items(), key=lambda kv: kv[1]):
                lines.append(f"    {rate:>6.0%}  {case_id}")
        lines.append("=" * 62)
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Runner
# --------------------------------------------------------------------------- #


async def run_case(
    runtime: FilingIntelRuntime, case: EvalCase, attempt: int
) -> RunResult:
    before = len(runtime.telemetry.events)
    started = time.perf_counter()
    try:
        response = await runtime.research(
            ResearchRequest(ticker=case.ticker, question=case.question)
        )
    except Exception as exc:
        return RunResult(
            case_id=case.case_id,
            attempt=attempt,
            passed=False,
            checks=[],
            latency_ms=(time.perf_counter() - started) * 1000,
            cost_usd=0.0,
            tool_calls=0,
            error=f"{type(exc).__name__}: {exc}",
        )

    tools_used = [
        e.tool
        for e in runtime.telemetry.events[before:]
        if e.type == "tool_call" and e.ok
    ]
    checks = grade(case, response, tools_used)
    return RunResult(
        case_id=case.case_id,
        attempt=attempt,
        passed=all(c.passed for c in checks),
        checks=checks,
        latency_ms=response.latency_ms,
        cost_usd=response.estimated_cost_usd,
        tool_calls=response.tool_calls_made,
    )


async def run_eval(
    runtime: FilingIntelRuntime,
    cases: list[EvalCase],
    repeats: int = 1,
    concurrency: int = 4,
) -> tuple[EvalReport, list[RunResult]]:
    semaphore = asyncio.Semaphore(concurrency)

    async def guarded(case: EvalCase, attempt: int) -> RunResult:
        async with semaphore:
            return await run_case(runtime, case, attempt)

    tasks = [
        guarded(case, attempt)
        for case in cases
        for attempt in range(repeats)
    ]
    results = await asyncio.gather(*tasks)

    report = EvalReport(cases=len(cases))
    by_case: dict[str, list[RunResult]] = defaultdict(list)
    for result in results:
        report.total_runs += 1
        report.total_cost_usd += result.cost_usd
        report.latencies_ms.append(result.latency_ms)
        by_case[result.case_id].append(result)

        if result.error:
            report.error_runs += 1
            report.errors_by_kind[result.error.split(":")[0]] += 1
        if result.passed:
            report.passed_runs += 1
        for check in result.checks:
            if not check.passed:
                report.check_failures[check.name] += 1

    for case_id, runs in by_case.items():
        report.per_case_pass_rate[case_id] = sum(r.passed for r in runs) / len(runs)
        if len({r.signature for r in runs}) == 1:
            report.fully_consistent_cases += 1

    return report, list(results)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #


def _write_report(path: str, report: EvalReport, results: list[RunResult]) -> None:
    Path(path).write_text(
        json.dumps(
            {
                "summary": report.to_dict(),
                "runs": [
                    {
                        "case_id": r.case_id,
                        "attempt": r.attempt,
                        "passed": r.passed,
                        "latency_ms": round(r.latency_ms, 1),
                        "cost_usd": round(r.cost_usd, 6),
                        "tool_calls": r.tool_calls,
                        "error": r.error,
                        "failed_checks": [c.name for c in r.checks if not c.passed],
                    }
                    for r in results
                ],
            },
            indent=2,
        )
        + "\n"
    )


async def _run(args: argparse.Namespace) -> tuple[EvalReport, list[RunResult]]:
    settings: Settings = get_settings()
    if args.offline:
        # Stub model, real EDGAR. Measures orchestration, not model quality.
        from filing_intel.cache import build_cache
        from filing_intel.data import EdgarClient, PriceClient
        from filing_intel.providers import DemoProvider

        cache = build_cache(settings.redis_url)
        runtime = FilingIntelRuntime(
            settings, DemoProvider(), cache, EdgarClient(settings),
            PriceClient(settings),
        )
    else:
        runtime = FilingIntelRuntime.build(settings)
    try:
        cases = load_dataset(args.dataset)
        return await run_eval(
            runtime, cases, repeats=args.repeats, concurrency=args.concurrency
        )
    finally:
        await runtime.aclose()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the filing-research eval suite.")
    parser.add_argument("--dataset", default="evals/dataset.jsonl")
    parser.add_argument("--repeats", type=int, default=1, help="Runs per case.")
    parser.add_argument("--concurrency", type=int, default=4)
    parser.add_argument("--json-out", default=None)
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use the deterministic stub model against real EDGAR data (no API key).",
    )
    parser.add_argument(
        "--min-accuracy",
        type=float,
        default=0.0,
        help="Exit non-zero below this accuracy, for CI gating.",
    )
    args = parser.parse_args()

    report, results = asyncio.run(_run(args))
    print(report.render())

    if args.json_out:
        _write_report(args.json_out, report, results)
        print(f"\nwrote {args.json_out}")

    return 0 if report.accuracy >= args.min_accuracy else 1


if __name__ == "__main__":
    raise SystemExit(main())
