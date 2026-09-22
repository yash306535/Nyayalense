"""Overview and review: the two analyses that describe a whole document.

Both share one cacheable prompt prefix and both run through the verifier before
anything is returned. Deterministic findings made at ingestion, such as amount
mismatches, are merged in here rather than asked of the model.
"""

import logging

from app.adapters.cache import cache_key
from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMOverview, LLMReview
from app.domain.audience import Audience
from app.domain.checklists import Checklist
from app.domain.enums import ChecklistStatus, InconsistencyKind, Severity
from app.domain.models import Document, VerificationReport
from app.domain.results import (
    ChecklistResult,
    Inconsistency,
    KeyDate,
    KeyTerm,
    MissingItem,
    Obligation,
    Overview,
    Party,
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
from app.services.grounding import ground, to_citation

logger = logging.getLogger(__name__)


async def build_overview(
    document: Document, audience: Audience, context: AnalysisContext
) -> Overview:
    """Produce the plain-language overview of a document.

    Args:
        document: The document under analysis.
        audience: The reader's role, language and reading level.
        context: The model adapter, settings, cache and packaged data.

    Returns:
        The overview, with every surviving statement verified.
    """
    key = cache_key(
        document_hash=document.id,
        operation=Task.OVERVIEW.value,
        model=context.model,
        params=audience.as_params(),
    )
    cached = context.cache.get(key)
    if isinstance(cached, Overview):
        return cached

    prompt = build(document, Task.OVERVIEW, audience)
    raw = (await context.client.generate(prompt, LLMOverview, task=Task.OVERVIEW)).data
    index = ClauseIndex(document)
    threshold = context.threshold

    summary, summary_report = ground(raw.summary, index, threshold=threshold)
    key_terms, term_reports = _ground_key_terms(raw, index, threshold=threshold)
    obligations, obligation_reports = _ground_obligations(raw, index, threshold=threshold)
    key_dates, date_reports = _ground_key_dates(raw, index, threshold=threshold)

    overview = Overview(
        summary=summary,
        parties=[
            Party(
                name=party.name,
                described_as=party.described_as,
                is_user=party.is_user,
                citations=[to_citation(citation) for citation in party.citations],
            )
            for party in raw.parties
        ],
        key_terms=key_terms,
        obligations=obligations,
        key_dates=key_dates,
        role=audience.role,
        reading_level=audience.reading_level.value,
        verification=merge_reports(
            [summary_report, *term_reports, *obligation_reports, *date_reports]
        ),
    )
    context.cache.set(key, overview)
    _log_verification("overview", overview.verification)
    return overview


def _ground_key_terms(
    raw: LLMOverview, index: ClauseIndex, *, threshold: int
) -> tuple[list[KeyTerm], list[VerificationReport]]:
    """Verify each key term, keeping unspecified terms as explicit absences."""
    terms: list[KeyTerm] = []
    reports: list[VerificationReport] = []
    for term in raw.key_terms:
        statements, report = ground(term.statements, index, threshold=threshold)
        reports.append(report)
        terms.append(
            KeyTerm(
                id=term.id,
                label=term.label,
                value=term.value if term.value and statements else None,
                statements=statements,
                verification=report,
            )
        )
    return terms, reports


def _ground_obligations(
    raw: LLMOverview, index: ClauseIndex, *, threshold: int
) -> tuple[list[Obligation], list[VerificationReport]]:
    """Verify each obligation, dropping any left with no evidence."""
    obligations: list[Obligation] = []
    reports: list[VerificationReport] = []
    for obligation in raw.obligations:
        statements, report = ground(obligation.statements, index, threshold=threshold)
        reports.append(report)
        if not statements:
            continue
        obligations.append(
            Obligation(
                who=obligation.who,
                what=obligation.what,
                timing=obligation.timing,
                timing_kind=obligation.timing_kind,
                consequence=obligation.consequence,
                statements=statements,
            )
        )
    return obligations, reports


def _ground_key_dates(
    raw: LLMOverview, index: ClauseIndex, *, threshold: int
) -> tuple[list[KeyDate], list[VerificationReport]]:
    """Verify each key date, dropping any left with no evidence."""
    dates: list[KeyDate] = []
    reports: list[VerificationReport] = []
    for date in raw.key_dates:
        statements, report = ground(date.statements, index, threshold=threshold)
        reports.append(report)
        if not statements:
            continue
        dates.append(
            KeyDate(
                title=date.title,
                date=date.date,
                timing_kind=date.timing_kind,
                description=date.description,
                statements=statements,
            )
        )
    return dates, reports


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
    _log_verification("review", review.verification)
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


def _log_verification(operation: str, report: VerificationReport) -> None:
    """Record how much of a result survived verification. Metadata only."""
    logger.info(
        "verification",
        extra={
            "operation": operation,
            "total": report.total,
            "verified": report.verified,
            "removed": report.removed_count,
        },
    )


__all__ = ["build_overview", "build_review"]
