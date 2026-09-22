"""Comparing two documents.

Alignment and diffing are deterministic, so only the pairs that actually differ
are sent to a model, and only to explain what the change means. In the
alternatives mode nothing is ranked: the difference is described and the reader
decides.
"""

import logging
from collections.abc import Mapping

from app.adapters.cache import cache_key, content_hash
from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMCompare
from app.domain.audience import Audience
from app.domain.diff import AlignedPair, align, count_changes
from app.domain.enums import ChangeKind, ChecklistStatus, CompareMode, Severity
from app.domain.models import Document, VerificationReport
from app.domain.results import (
    AlternativeRow,
    ChecklistResult,
    ClausePair,
    CompareResult,
    Review,
)
from app.domain.verification import ClauseIndex, merge_reports
from app.prompts.builder import build
from app.services.analysis import build_review
from app.services.context import AnalysisContext
from app.services.grounding import ground

logger = logging.getLogger(__name__)

#: How many changed pairs are explained. Beyond this the table is unreadable
#: anyway, and the cost of explaining every pair is not worth paying.
MAX_EXPLAINED_PAIRS = 25


async def compare_documents(
    before: Document,
    after: Document,
    *,
    mode: CompareMode,
    audience: Audience,
    context: AnalysisContext,
) -> CompareResult:
    """Compare two documents in the requested mode.

    Args:
        before: The earlier version, or document A.
        after: The later version, or document B.
        mode: Versions of one document, or two competing alternatives.
        audience: The reader's role, language and reading level.
        context: The model adapter, settings, cache and packaged data.

    Returns:
        The comparison, with every surviving statement verified.
    """
    key = cache_key(
        document_hash=pair_id(before, after),
        operation=f"{Task.COMPARE.value}:{mode.value}",
        model=context.model,
        params=audience.as_params(),
    )
    cached = context.cache.get(key)
    if isinstance(cached, CompareResult):
        return cached

    if mode is CompareMode.VERSIONS:
        result = await _compare_versions(before, after, audience=audience, context=context)
    else:
        result = await _compare_alternatives(before, after, audience=audience, context=context)

    context.cache.set(key, result)
    logger.info(
        "compare_done",
        extra={"mode": mode.value, "rows": len(result.pairs) + len(result.rows), **result.counts},
    )
    return result


async def _compare_versions(
    before: Document, after: Document, *, audience: Audience, context: AnalysisContext
) -> CompareResult:
    """Align two versions clause by clause, then explain only what changed."""
    pairs = align(before.clauses, after.clauses)
    changed = [pair for pair in pairs if pair.change is ChangeKind.CHANGED][:MAX_EXPLAINED_PAIRS]

    explanations: dict[str, ClausePair] = {}
    reports: list[VerificationReport] = []
    if changed:
        explanations, reports = await _explain_changes(
            changed, before=before, after=after, audience=audience, context=context
        )

    return CompareResult(
        mode=CompareMode.VERSIONS,
        pairs=[_to_clause_pair(pair, explanations) for pair in pairs],
        counts=count_changes(pairs),
        verification=merge_reports(reports),
    )


def _to_clause_pair(pair: AlignedPair, explanations: dict[str, ClausePair]) -> ClausePair:
    """Render one aligned pair for the table, attaching its explanation."""
    explained = explanations.get(pair.label)
    return ClausePair(
        change=pair.change,
        before_clause_id=pair.before.id if pair.before else None,
        after_clause_id=pair.after.id if pair.after else None,
        label=pair.label,
        before_text=pair.before.text if pair.before else "",
        after_text=pair.after.text if pair.after else "",
        what_changed=explained.what_changed if explained else [],
        impact=explained.impact if explained else "",
        severity=explained.severity if explained else Severity.LOW,
    )


async def _explain_changes(
    changed: list[AlignedPair],
    *,
    before: Document,
    after: Document,
    audience: Audience,
    context: AnalysisContext,
) -> tuple[dict[str, ClausePair], list[VerificationReport]]:
    """Ask the model what the changed pairs mean, then verify its answer.

    The two versions are presented as one document of prefixed clauses, so a
    quote can be verified against whichever version it came from.
    """
    combined = _combined_document(changed, before=before, after=after)
    prompt = build(
        combined,
        Task.COMPARE,
        audience,
        substitutions={"pairs": _describe_pairs(changed)},
    )
    raw = (await context.client.generate(prompt, LLMCompare, task=Task.COMPARE)).data

    index = ClauseIndex(combined)
    explanations: dict[str, ClausePair] = {}
    reports: list[VerificationReport] = []
    for change in raw.changes:
        statements, report = ground(change.statements, index, threshold=context.threshold)
        reports.append(report)
        explanations[change.clause_label] = ClausePair(
            change=ChangeKind.CHANGED,
            label=change.clause_label,
            what_changed=statements,
            impact=change.impact,
            severity=change.severity,
        )
    return explanations, reports


def _combined_document(
    changed: list[AlignedPair], *, before: Document, after: Document
) -> Document:
    """Build a two-sided document holding only the clauses that changed."""
    clauses = []
    for pair in changed:
        if pair.before is not None:
            clauses.append(
                pair.before.model_copy(
                    update={"id": f"OLD-{pair.before.id}", "heading": f"Before: {pair.label}"}
                )
            )
        if pair.after is not None:
            clauses.append(
                pair.after.model_copy(
                    update={"id": f"NEW-{pair.after.id}", "heading": f"After: {pair.label}"}
                )
            )
    return Document(
        id=pair_id(before, after),
        doc_type=after.doc_type,
        language=after.language,
        clauses=clauses,
    )


def pair_id(before: Document, after: Document) -> str:
    """Derive one short, stable id for a pair of documents."""
    return content_hash([before.id, after.id])


def _describe_pairs(changed: list[AlignedPair]) -> str:
    """List the changed clause labels for the prompt."""
    return "\n".join(f"- Clause {pair.label}" for pair in changed)


async def _compare_alternatives(
    before: Document, after: Document, *, audience: Audience, context: AnalysisContext
) -> CompareResult:
    """Review both documents, then line the two reviews up by checklist item."""
    review_a = await build_review(before, audience, context)
    review_b = await build_review(after, audience, context)

    checklist = context.registry.checklist(before.doc_type)
    titles = {item.id: item.title for item in checklist.items}
    by_id_a = {result.item_id: result for result in review_a.checklist}
    by_id_b = {result.item_id: result for result in review_b.checklist}

    rows = [
        _alternative_row(item_id, title, by_id_a, by_id_b)
        for item_id, title in titles.items()
        if item_id in by_id_a or item_id in by_id_b
    ]

    return CompareResult(
        mode=CompareMode.ALTERNATIVES,
        rows=rows,
        counts={
            "topics": len(rows),
            "differs": sum(row.a_status is not row.b_status for row in rows),
        },
        verification=merge_reports([review_a.verification, review_b.verification]),
    )


def _alternative_row(
    item_id: str,
    title: str,
    by_id_a: Mapping[str, ChecklistResult],
    by_id_b: Mapping[str, ChecklistResult],
) -> AlternativeRow:
    """Build one topic row from the two reviews."""
    side_a = by_id_a.get(item_id)
    side_b = by_id_b.get(item_id)
    status_a = side_a.status if side_a else ChecklistStatus.NOT_FOUND
    status_b = side_b.status if side_b else ChecklistStatus.NOT_FOUND

    return AlternativeRow(
        topic_id=item_id,
        topic=title,
        a_status=status_a,
        b_status=status_b,
        a_statements=list(side_a.statements) if side_a else [],
        b_statements=list(side_b.statements) if side_b else [],
        difference=_describe_difference(status_a, status_b),
    )


def _describe_difference(status_a: ChecklistStatus, status_b: ChecklistStatus) -> str:
    """Describe the difference neutrally, without preferring either document.

    Args:
        status_a: Outcome for document A.
        status_b: Outcome for document B.

    Returns:
        A neutral sentence. The app never says which document is better.
    """
    if status_a is status_b:
        return "Both documents are the same on this point."
    if status_a is ChecklistStatus.FOUND:
        return "Document A covers this; document B does not."
    if status_b is ChecklistStatus.FOUND:
        return "Document B covers this; document A does not."
    return "The two documents differ on this point."


__all__ = ["Review", "compare_documents"]
