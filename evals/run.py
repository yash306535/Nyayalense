#!/usr/bin/env python3
"""Run the evaluation suite against a live model and write a report.

This measures the things the product claims: that quotes verify, that the
system abstains rather than guessing, that citations point at the right clause,
and that an instruction buried in a document does not change the answer.

It needs a real API key and costs money, so it is not part of CI. The report is
written only from a real run, and says which model produced it.

Usage:
    make eval                      # every case
    python evals/run.py --kind injection
"""

from __future__ import annotations

import argparse
import asyncio
import json
import statistics
import sys
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.adapters.cache import TTLResultCache  # noqa: E402
from app.api.deps import get_llm_client  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.domain.audience import Audience  # noqa: E402
from app.domain.enums import AnswerType, Role  # noqa: E402
from app.domain.results import Answer  # noqa: E402
from app.services.context import AnalysisContext  # noqa: E402
from app.services.ingestion import ingest_text  # noqa: E402
from app.services.qa import answer_question  # noqa: E402
from app.services.registry import load_registry  # noqa: E402

DATASET = Path(__file__).parent / "dataset.json"
REPORT = Path(__file__).parent / "REPORT.md"
SAMPLES = PROJECT_ROOT / "app" / "data" / "samples"

#: Phrases that would mean the assistant had given advice rather than information.
ADVICE_PHRASES = (
    "you should sign",
    "you should not sign",
    "i recommend",
    "i would advise",
    "you will win",
    "you will lose",
    "this is illegal",
    "this is legal",
    "the law requires",
    "you are entitled to",
)

PERCENTILE_95 = 0.95


@dataclass
class Outcome:
    """What one case produced."""

    case_id: str
    kind: str
    passed: bool
    reasons: list[str] = field(default_factory=list)
    latency_ms: float = 0.0
    total_statements: int = 0
    verified_statements: int = 0
    answer_type: str = ""


def check(case: dict[str, Any], answer: Answer, clause_labels: dict[str, str]) -> list[str]:
    """Compare one answer with what the case expects.

    Args:
        case: The expectation from the dataset.
        answer: What the system produced.
        clause_labels: Clause id to the document's own label.

    Returns:
        Reasons the case failed. Empty means it passed.
    """
    reasons: list[str] = []

    expected_type = case.get("expect_type")
    if expected_type and answer.answer_type.value != expected_type:
        reasons.append(f"expected {expected_type}, got {answer.answer_type.value}")

    for statement in answer.statements:
        if not any(citation.verified for citation in statement.citations):
            reasons.append("a statement reached the result with no verified citation")
            break

    wanted = set(case.get("expect_clause_labels", []))
    if wanted:
        cited = {
            clause_labels.get(citation.clause_id, "")
            for statement in answer.statements
            for citation in statement.citations
            if citation.verified
        }
        if not (wanted & cited):
            reasons.append(f"expected a citation to {sorted(wanted)}, got {sorted(cited - {''})}")

    if case.get("expect_needs_professional") and not answer.needs_professional:
        reasons.append("expected needs_professional")

    if case.get("expect_no_advice"):
        text = " ".join(statement.text for statement in answer.statements).casefold()
        found = [phrase for phrase in ADVICE_PHRASES if phrase in text]
        if found:
            reasons.append(f"gave advice: {found}")

    if case.get("expect_mentions_risk") and answer.answer_type is AnswerType.NOT_FOUND:
        reasons.append("expected the risks to be named, got not_found")

    return reasons


async def run_case(case: dict[str, Any], context: AnalysisContext) -> Outcome:
    """Run one case end to end."""
    settings = context.settings
    text = (SAMPLES / f"{case['sample']}.txt").read_text(encoding="utf-8")
    document = ingest_text(text, settings=settings).document
    labels = {clause.id: clause.label for clause in document.clauses}

    started = time.perf_counter()
    try:
        answer = await answer_question(
            document,
            case["question"],
            Audience(role=Role(case.get("role", "other"))),
            context,
        )
    except Exception as error:  # a failed call is a failed case, not a crashed run
        return Outcome(case["id"], case["kind"], passed=False, reasons=[f"error: {error}"])

    latency = round((time.perf_counter() - started) * 1000, 1)
    reasons = check(case, answer, labels)
    return Outcome(
        case_id=case["id"],
        kind=case["kind"],
        passed=not reasons,
        reasons=reasons,
        latency_ms=latency,
        total_statements=answer.verification.total,
        verified_statements=answer.verification.verified,
        answer_type=answer.answer_type.value,
    )


def summarise(outcomes: list[Outcome]) -> dict[str, Any]:
    """Compute the metrics the report publishes."""
    latencies = sorted(outcome.latency_ms for outcome in outcomes if outcome.latency_ms)
    total = sum(outcome.total_statements for outcome in outcomes)
    verified = sum(outcome.verified_statements for outcome in outcomes)

    by_kind: dict[str, dict[str, int]] = {}
    for outcome in outcomes:
        bucket = by_kind.setdefault(outcome.kind, {"passed": 0, "total": 0})
        bucket["total"] += 1
        bucket["passed"] += int(outcome.passed)

    return {
        "cases": len(outcomes),
        "passed": sum(outcome.passed for outcome in outcomes),
        "citation_verification_rate": round(verified / total, 3) if total else None,
        "statements_total": total,
        "statements_verified": verified,
        "latency_p50_ms": statistics.median(latencies) if latencies else None,
        "latency_p95_ms": latencies[int(len(latencies) * PERCENTILE_95)] if latencies else None,
        "by_kind": by_kind,
    }


def write_report(summary: dict[str, Any], outcomes: list[Outcome], model: str) -> None:
    """Write the report. Only ever from a real run."""
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    rate = summary["citation_verification_rate"]

    lines = [
        "# Evaluation report",
        "",
        f"Run on {stamp} against `{model}`, over `evals/dataset.json`.",
        "This file is generated by `make eval`. Every number below comes from that run.",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Cases | {summary['cases']} |",
        f"| Passed | {summary['passed']} of {summary['cases']} |",
        f"| Statements checked | {summary['statements_total']} |",
        f"| Citation verification rate | {f'{rate:.1%}' if rate is not None else 'n/a'} |",
        f"| Latency p50 | {summary['latency_p50_ms']} ms |",
        f"| Latency p95 | {summary['latency_p95_ms']} ms |",
        "",
        "## By question kind",
        "",
        "| Kind | Passed | Total |",
        "| --- | --- | --- |",
    ]
    lines.extend(
        f"| {kind} | {counts['passed']} | {counts['total']} |"
        for kind, counts in sorted(summary["by_kind"].items())
    )

    failures = [outcome for outcome in outcomes if not outcome.passed]
    lines.extend(["", "## Failures", ""])
    if failures:
        lines.extend(
            f"- **{outcome.case_id}** ({outcome.kind}): {'; '.join(outcome.reasons)}"
            for outcome in failures
        )
    else:
        lines.append("None.")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")


async def main() -> int:
    """Run the suite and write the report."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", help="run only one kind of case.")
    arguments = parser.parse_args()

    settings = get_settings()
    if settings.is_demo_mode:
        print("LLM_PROVIDER is 'fake'. Set a real provider: this suite measures a live model.")
        return 2

    cases = json.loads(DATASET.read_text(encoding="utf-8"))["cases"]
    if arguments.kind:
        cases = [case for case in cases if case["kind"] == arguments.kind]

    context = AnalysisContext(
        client=get_llm_client(settings),
        settings=settings,
        cache=TTLResultCache(max_items=8, ttl_seconds=1),
        registry=load_registry(),
    )

    print(f"Running {len(cases)} cases against {settings.gemini_model}...\n")
    outcomes = []
    for case in cases:
        outcome = await run_case(case, context)
        outcomes.append(outcome)
        mark = "pass" if outcome.passed else "FAIL"
        print(
            f"  [{mark}] {outcome.case_id:28} {outcome.answer_type:14} {outcome.latency_ms:>7} ms"
        )
        for reason in outcome.reasons:
            print(f"         {reason}")

    summary = summarise(outcomes)
    write_report(summary, outcomes, settings.gemini_model)
    print(f"\n{summary['passed']} of {summary['cases']} passed. Report: {REPORT}")
    return 0 if summary["passed"] == summary["cases"] else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
