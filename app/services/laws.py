"""Looking up a statutory provision and comparing the old text with the new.

The mapping itself is pure data: a model is never asked what a section maps to.
A model is put to two uses, and only where there is real statute text to check
it against: describing the difference between two stored provision texts, and
answering a general legal question from whichever stored provisions match it.
Both go through the same verifier as everything else.
"""

import hashlib
import logging
from dataclasses import dataclass, field

from app.adapters.cache import cache_key
from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMAnswer
from app.domain.audience import Audience
from app.domain.diff import DiffToken, word_diff
from app.domain.enums import AnswerType, ChangeType, DocType, LawAct
from app.domain.laws.lookup import LawIndex
from app.domain.laws.models import LawMapping, LawReference, Provision, ProvisionRef
from app.domain.laws.references import parse_query
from app.domain.models import Clause, Document, Statement, VerificationReport
from app.domain.results import Answer
from app.domain.verification import ClauseIndex, merge_reports
from app.prompts.builder import build
from app.services.context import AnalysisContext
from app.services.grounding import ground

logger = logging.getLogger(__name__)

OLD_CLAUSE_ID = "OLD"
NEW_CLAUSE_ID = "NEW"


@dataclass(frozen=True, slots=True)
class LookupResult:
    """What a search of the law data found.

    Attributes:
        query: What the user typed.
        reference: The parsed reference, when the query named an act.
        mappings: The matching rows, already filtered by review status.
        provisions: Stored texts for the provisions involved, keyed ``act:section``.
        suggestions: Near matches, when nothing was found.
    """

    query: str
    reference: LawReference | None = None
    mappings: list[LawMapping] = field(default_factory=list)
    provisions: dict[str, Provision] = field(default_factory=dict)
    suggestions: list[str] = field(default_factory=list)


def lookup(query: str, index: LawIndex, *, include_unreviewed: bool) -> LookupResult:
    """Find every mapping for a reference, or a topic, the user typed.

    Args:
        query: What the user typed. Either a citation in any recognised form
            (``"IPC 420"``), or a plain topic (``"rape"``) matched against
            what each mapping's own title says it is about.
        index: The loaded law index.
        include_unreviewed: Whether rows still marked ``extracted`` count.

    Returns:
        The result. A query that names neither a citation nor a topic the data
        covers returns empty lists rather than a guess.
    """
    reference = parse_query(query)
    if reference is not None:
        hits = index.lookup(reference, include_unreviewed=include_unreviewed)
        suggestions = [] if hits else index.suggest(reference)
    else:
        hits = index.search_by_topic(query, include_unreviewed=include_unreviewed)
        suggestions = []

    mappings = [hit.mapping for hit in hits]
    return LookupResult(
        query=query,
        reference=reference,
        mappings=mappings,
        provisions=_stored_texts(mappings, index),
        suggestions=suggestions,
    )


def _stored_texts(mappings: list[LawMapping], index: LawIndex) -> dict[str, Provision]:
    """Collect whichever provision texts are packaged for these rows."""
    texts: dict[str, Provision] = {}
    for mapping in mappings:
        for reference in [mapping.old, *mapping.new]:
            provision = index.provision(reference.act, reference.section)
            if provision is not None:
                texts[provision.key] = provision
    return texts


def provision_diff(old: Provision | None, new: Provision | None) -> list[DiffToken]:
    """Diff two stored provision texts.

    Args:
        old: The provision in the replaced code, if it is stored.
        new: Its counterpart in the new code, if it is stored.

    Returns:
        Diff tokens, or an empty list when either text is missing. Nothing is
        guessed: with no stored text there is no comparison to show.
    """
    if old is None or new is None:
        return []
    return word_diff(old.text, new.text)


def browse(index: LawIndex, kind: str, *, include_unreviewed: bool) -> list[LawMapping]:
    """List notable changes for the browse lists.

    Args:
        index: The loaded law index.
        kind: ``"new"`` for provisions with no old counterpart, ``"removed"``
            for old provisions the new code does not carry forward.
        include_unreviewed: Whether rows still marked ``extracted`` count.

    Returns:
        The matching rows.
    """
    change_type = ChangeType.NEW_PROVISION if kind == "new" else ChangeType.NO_DIRECT_EQUIVALENT
    return index.changes(change_type, include_unreviewed=include_unreviewed)


async def explain_change(
    mapping: LawMapping,
    provisions: dict[str, Provision],
    *,
    audience: Audience,
    context: AnalysisContext,
) -> Answer | None:
    """Describe the difference between two stored provision texts.

    The two texts are treated as a two-clause document, so the explanation goes
    through exactly the same verifier as an explanation of a contract. With no
    stored texts there is nothing to ground against, so nothing is generated.

    Args:
        mapping: The mapping row being compared.
        provisions: Stored texts, keyed ``act:section``.
        audience: The reader's language and reading level.
        context: The model adapter, settings, cache and packaged data.

    Returns:
        The verified explanation, or ``None`` when either text is missing.
    """
    old = provisions.get(mapping.old.key)
    new = provisions.get(mapping.new[0].key) if mapping.new else None
    if old is None or new is None:
        return None

    key = cache_key(
        document_hash=f"law-{mapping.old.key}",
        operation=Task.LAW_CHANGE.value,
        model=context.model,
        params=audience.as_params(),
    )
    cached = context.cache.get(key)
    if isinstance(cached, Answer):
        return cached

    document = _as_document(old, new)
    prompt = build(document, Task.LAW_CHANGE, audience)
    raw = (await context.client.generate(prompt, LLMAnswer, task=Task.LAW_CHANGE)).data

    statements, report = ground(raw.statements, ClauseIndex(document), threshold=context.threshold)
    answer = Answer(
        question=f"What changed between {mapping.old.display} and {mapping.new[0].display}?",
        answer_type=raw.answer_type if statements else AnswerType.NOT_FOUND,
        statements=statements,
        verification=merge_reports([report]),
    )
    context.cache.set(key, answer)
    logger.info(
        "law_change_explained",
        extra={"old": mapping.old.key, "verified": report.verified, "total": report.total},
    )
    return answer


def _as_document(old: Provision, new: Provision) -> Document:
    """Present two provision texts as a two-clause document for verification."""
    return Document(
        id=f"law-{old.key}",
        doc_type=DocType.GENERAL_CONTRACT,
        clauses=[
            Clause(id=OLD_CLAUSE_ID, label=old.display, heading=old.title, text=old.text),
            Clause(id=NEW_CLAUSE_ID, label=new.display, heading=new.title, text=new.text),
        ],
    )


@dataclass(frozen=True, slots=True)
class LegalQAResult:
    """A general legal question, answered from whichever provisions matched it.

    Attributes:
        question: What the reader asked.
        matched: The sections the answer was allowed to draw from, for showing
            as citations even where a statement did not use them.
        answer: The verified answer. ``not_found`` when nothing matched, or
            when nothing in the matched text supported an answer.
    """

    question: str
    matched: list[ProvisionRef]
    answer: Answer


async def answer_legal_question(
    question: str, audience: Audience, context: AnalysisContext
) -> LegalQAResult:
    """Answer a general legal question from the packaged statute text alone.

    This is the one place a question is answered with no document behind it.
    What stands in for the document is a handful of real, stored provisions
    matched to the question's own words -- never the model's memory of what a
    law says. With no matching provision, or nothing in the matched text that
    verifies, the answer is ``not_found``, the same as document Q&A.

    Args:
        question: The reader's question.
        audience: The reader's language and reading level.
        context: The model adapter, settings, cache and packaged data.

    Returns:
        The matched sections and the verified answer.
    """
    provisions = context.registry.laws.matching_provisions(question)
    if not provisions:
        return LegalQAResult(
            question=question,
            matched=[],
            answer=Answer(
                question=question,
                answer_type=AnswerType.NOT_FOUND,
                verification=VerificationReport(),
            ),
        )

    matched = [
        ProvisionRef(act=provision.act, section=provision.section, title=provision.title)
        for provision in provisions
    ]
    key = cache_key(
        document_hash=_legal_qa_cache_id(provisions),
        operation=Task.LEGAL_QA.value,
        model=context.model,
        params={**audience.as_params(), "q": question},
    )
    cached = context.cache.get(key)
    if isinstance(cached, LegalQAResult):
        return cached

    document = _legal_qa_document(question, provisions)
    prompt = build(document, Task.LEGAL_QA, audience, question=question)
    raw = (await context.client.generate(prompt, LLMAnswer, task=Task.LEGAL_QA)).data
    index = ClauseIndex(document)
    statements, report = ground(raw.statements, index, threshold=context.threshold)

    answer_type = raw.answer_type
    if not statements and answer_type in {AnswerType.DIRECT, AnswerType.INTERPRETATION}:
        answer_type = AnswerType.NOT_FOUND

    result = LegalQAResult(
        question=question,
        matched=matched,
        answer=Answer(
            question=question,
            answer_type=answer_type,
            statements=statements,
            needs_professional=raw.needs_professional,
            questions_for_professional=raw.questions_for_professional,
            related_clause_ids=[
                clause_id for clause_id in raw.related_clause_ids if index.clause(clause_id)
            ],
            verification=report,
        ),
    )
    context.cache.set(key, result)
    logger.info(
        "legal_qa_answered",
        extra={
            "matched": len(provisions),
            "answer_type": result.answer.answer_type.value,
            "verified": report.verified,
            "total": report.total,
        },
    )
    return result


def _legal_qa_cache_id(provisions: list[Provision]) -> str:
    """A stable id for a set of matched provisions, for the cache key."""
    joined = "|".join(sorted(provision.key for provision in provisions))
    return f"legalqa-{hashlib.sha256(joined.encode()).hexdigest()[:16]}"


def _legal_qa_document(question: str, provisions: list[Provision]) -> Document:
    """Present matched provisions as a document, real statute text as clauses."""
    return Document(
        id=_legal_qa_cache_id(provisions),
        doc_type=DocType.GENERAL_CONTRACT,
        title=question[:300],
        clauses=[
            Clause(
                id=provision.key.upper().replace(":", "-"),
                label=provision.display,
                heading=provision.title[:300],
                text=provision.text,
                page=provision.source.page or 1,
            )
            for provision in provisions
        ],
    )


def references_with_mappings(
    references: list[LawReference], index: LawIndex, *, include_unreviewed: bool
) -> list[tuple[LawReference, list[LawMapping]]]:
    """Attach mappings to the references found in a document.

    Args:
        references: References detected at ingestion.
        index: The loaded law index.
        include_unreviewed: Whether rows still marked ``extracted`` count.

    Returns:
        Each reference with whatever the data says about it, which may be
        nothing.
    """
    return [
        (
            reference,
            [hit.mapping for hit in index.lookup(reference, include_unreviewed=include_unreviewed)],
        )
        for reference in references
    ]


def old_acts_only(references: list[LawReference]) -> list[LawReference]:
    """Keep only references to the codes replaced on 1 July 2024."""
    return [reference for reference in references if reference.act.is_old]


__all__ = [
    "LawAct",
    "LegalQAResult",
    "LookupResult",
    "Statement",
    "answer_legal_question",
    "browse",
    "explain_change",
    "lookup",
    "old_acts_only",
    "provision_diff",
    "references_with_mappings",
]
