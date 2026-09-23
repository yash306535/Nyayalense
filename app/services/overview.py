"""The plain-language overview of a whole document.

Summary, parties, key terms, obligations and dates. A term the document
does not specify comes back as an explicit absence, never as what such
documents usually contain.
"""

import logging

from app.adapters.cache import cache_key
from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMOverview
from app.domain.audience import Audience
from app.domain.models import Document, VerificationReport
from app.domain.results import (
    KeyDate,
    KeyTerm,
    Obligation,
    Overview,
    Party,
)
from app.domain.verification import ClauseIndex, merge_reports
from app.prompts.builder import build
from app.services.context import AnalysisContext
from app.services.grounding import ground, to_citation
from app.services.reporting import log_verification

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
    overview = _verify(raw, document, audience, threshold=context.threshold)

    context.cache.set(key, overview)
    log_verification("overview", overview.verification)
    return overview


def _verify(
    raw: LLMOverview, document: Document, audience: Audience, *, threshold: int
) -> Overview:
    """Put every part of a proposed overview through the verifier."""
    index = ClauseIndex(document)
    summary, summary_report = ground(raw.summary, index, threshold=threshold)
    key_terms, term_reports = _ground_key_terms(raw, index, threshold=threshold)
    obligations, obligation_reports = _ground_obligations(raw, index, threshold=threshold)
    key_dates, date_reports = _ground_key_dates(raw, index, threshold=threshold)

    return Overview(
        summary=summary,
        parties=[
            Party(
                name=party.name,
                described_as=party.described_as,
                is_user=party.is_user,
                citations=[
                    citation
                    for citation in (to_citation(citation) for citation in party.citations)
                    if citation is not None
                ],
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
