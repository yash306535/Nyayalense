"""The review: checklist, risks, missing protections and contradictions.

The checklist is curated data and is labelled as review prompts rather than
legal rules. An item the model calls found without evidence is recorded as
not found, and a contradiction needs a verified quote from each of two
clauses.
"""

import logging

from app.adapters.cache import cache_key
from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMReview
from app.domain.audience import Audience
from app.domain.checklists import Checklist
from app.domain.enums import ChecklistStatus, InconsistencyKind, Severity
from app.domain.models import Document, VerificationReport
from app.domain.results import (
    ChecklistResult,
    Inconsistency,
    MissingItem,
    Review,
    Risk,
)
from app.domain.verification import (
    CLAUSES_PER_CONTRADICTION,
    ClauseIndex,
    both_sides_verified,
    merge_reports,
)
from app.prompts.builder import build
from app.services.context import AnalysisContext
from app.services.grounding import ground
from app.services.reporting import log_verification

logger = logging.getLogger(__name__)


async def build_review(document: Document, audience: Audience, context: AnalysisContext) -> Review:
    """Produce the checklist, risks, missing protections and contradictions.

    Args:
        document: The document under analysis.
        audience: The reader's role, language and reading level.
        context: The model adapter, settings, cache and packaged data.

    Returns:
        The review, with every surviving statement verified.
    """
    checklist: Checklist = context.registry.checklist(document.doc_type)
    key = cache_key(
        document_hash=document.id,
        operation=Task.REVIEW.value,
        model=context.model,
        params=audience.as_params(),
    )
    cached = context.cache.get(key)
    if isinstance(cached, Review):
        return cached

    prompt = build(
        document,
        Task.REVIEW,
        audience,
        substitutions={"checklist": checklist.as_prompt_lines(audience.role)},
    )
    raw = (await context.client.generate(prompt, LLMReview, task=Task.REVIEW)).data
    index = ClauseIndex(document)
    threshold = context.threshold

    results, missing, checklist_reports = _ground_checklist(
        raw, checklist, index, threshold=threshold
    )
    risks, risk_reports = _ground_risks(raw, index, threshold=threshold)
    inconsistencies, contradiction_reports = _ground_contradictions(
        raw, document, index, threshold=threshold
    )

    review = Review(
        checklist=results,
        risks=risks,
        missing=missing,
        inconsistencies=inconsistencies,
        role=audience.role,
        verification=merge_reports([*checklist_reports, *risk_reports, *contradiction_reports]),
    )
    context.cache.set(key, review)
    log_verification("review", review.verification)
    return review


def _ground_checklist(
    raw: LLMReview, checklist: Checklist, index: ClauseIndex, *, threshold: int
) -> tuple[list[ChecklistResult], list[MissingItem], list[VerificationReport]]:
    """Verify each checklist outcome and turn absences into missing protections."""
    by_id = {item.id: item for item in checklist.items}
    results: list[ChecklistResult] = []
    missing: list[MissingItem] = []
    reports: list[VerificationReport] = []

    for outcome in raw.checklist:
        item = by_id.get(outcome.item_id)
        if item is None:
            continue
        statements, report = ground(outcome.statements, index, threshold=threshold)
        reports.append(report)
        # An item the model called "found" but could not evidence is not found.
        status = outcome.status if statements else ChecklistStatus.NOT_FOUND
        results.append(
            ChecklistResult(
                item_id=item.id,
                title=item.title,
                status=status,
                statements=statements,
                question_to_ask=item.question_to_ask,
            )
        )
        if status is ChecklistStatus.NOT_FOUND:
            missing.append(
                MissingItem(
                    id=item.id,
                    title=item.title,
                    why_it_matters=item.why_it_matters,
                    closest_clause_ids=[
                        clause_id
                        for clause_id in outcome.closest_clause_ids
                        if index.clause(clause_id) is not None
                    ],
                    question_to_ask=item.question_to_ask,
                )
            )
    return results, missing, reports


def _ground_risks(
    raw: LLMReview, index: ClauseIndex, *, threshold: int
) -> tuple[list[Risk], list[VerificationReport]]:
    """Verify each risk, dropping any the document does not evidence."""
    risks: list[Risk] = []
    reports: list[VerificationReport] = []
    for position, risk in enumerate(raw.risks, start=1):
        statements, report = ground(risk.statements, index, threshold=threshold)
        reports.append(report)
        if not statements:
            continue
        risks.append(
            Risk(
                id=f"risk-{position}",
                category=risk.category,
                title=risk.title,
                severity=risk.severity,
                explanation=risk.explanation,
                statements=statements,
                question_to_ask=risk.question_to_ask,
            )
        )
    return _by_severity(risks), reports


def _by_severity(risks: list[Risk]) -> list[Risk]:
    """Order risks so the most serious appear first."""
    order = {Severity.HIGH: 0, Severity.MEDIUM: 1, Severity.LOW: 2}
    return sorted(risks, key=lambda risk: order[risk.severity])


def _ground_contradictions(
    raw: LLMReview, document: Document, index: ClauseIndex, *, threshold: int
) -> tuple[list[Inconsistency], list[VerificationReport]]:
    """Merge deterministic amount mismatches with verified model contradictions."""
    inconsistencies = [
        Inconsistency(
            kind=InconsistencyKind.AMOUNT_MISMATCH,
            title="An amount is written two different ways",
            explanation=(
                f"This clause says {mismatch.in_digits} in digits but {mismatch.in_words} in words."
            ),
            statements=[],
        )
        for mismatch in document.amount_mismatches
    ]

    reports: list[VerificationReport] = []
    for contradiction in raw.contradictions:
        statements, report = ground(contradiction.statements, index, threshold=threshold)
        reports.append(report)
        # A contradiction is a claim about two clauses at once, so it needs two.
        cited = {citation.clause_id for statement in statements for citation in statement.citations}
        supported = any(both_sides_verified(statement) for statement in statements) or (
            len(cited) >= CLAUSES_PER_CONTRADICTION
        )
        if not supported:
            continue
        inconsistencies.append(
            Inconsistency(
                kind=InconsistencyKind.CONTRADICTION,
                title=contradiction.title,
                explanation=contradiction.explanation,
                statements=statements,
            )
        )
    return inconsistencies, reports
