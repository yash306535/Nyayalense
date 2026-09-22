"""Grounded question answering.

The interesting case is the one where the document does not answer. A general
assistant will reach for what contracts usually say; here, an unsupported answer
is downgraded to ``not_found`` and the user is offered a question to put to the
other party instead.
"""

import logging

from app.adapters.cache import cache_key
from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMAnswer
from app.domain.audience import Audience
from app.domain.checklists import Checklist
from app.domain.enums import AnswerType
from app.domain.models import Document
from app.domain.results import Answer
from app.domain.verification import ClauseIndex
from app.prompts.builder import build, format_history
from app.services.context import AnalysisContext
from app.services.grounding import ground

logger = logging.getLogger(__name__)

#: Offered when the document is silent, so the user still leaves with a next step.
DEFAULT_QUESTION_TO_ASK = "Could you confirm this in writing before I sign?"

NOT_FOUND_NOTE = "We couldn't verify an answer in your document."


async def answer_question(
    document: Document,
    question: str,
    audience: Audience,
    context: AnalysisContext,
    *,
    history: list[tuple[str, str]] | None = None,
) -> Answer:
    """Answer one question using only the document.

    Args:
        document: The document under analysis.
        question: The reader's question.
        audience: The reader's role, language and reading level.
        context: The model adapter, settings, cache and packaged data.
        history: Recent ``(question, answer)`` turns, for follow-ups.

    Returns:
        The answer, downgraded to ``not_found`` if nothing could be verified.
    """
    turns = history or []
    checklist: Checklist | None = context.registry.checklists.get(document.doc_type)
    key = cache_key(
        document_hash=document.id,
        operation=Task.QA.value,
        model=context.model,
        params={**audience.as_params(), "q": question, "history": turns},
    )
    cached = context.cache.get(key)
    if isinstance(cached, Answer):
        return cached

    prompt = build(
        document,
        Task.QA,
        audience,
        substitutions={"history": format_history(turns)},
        question=question,
    )
    raw = (await context.client.generate(prompt, LLMAnswer, task=Task.QA)).data
    index = ClauseIndex(document)
    statements, report = ground(raw.statements, index, threshold=context.threshold)

    answer_type = raw.answer_type
    if not statements and answer_type in {AnswerType.DIRECT, AnswerType.INTERPRETATION}:
        answer_type = AnswerType.NOT_FOUND

    answer = Answer(
        question=question,
        answer_type=answer_type,
        statements=statements,
        needs_professional=raw.needs_professional,
        questions_for_professional=raw.questions_for_professional,
        suggested_question_to_other_party=_fallback_question(
            answer_type, raw.suggested_question_to_other_party, checklist
        ),
        related_clause_ids=[
            clause_id for clause_id in raw.related_clause_ids if index.clause(clause_id) is not None
        ],
        verification=report,
    )
    context.cache.set(key, answer)
    logger.info(
        "qa_answered",
        extra={
            "answer_type": answer.answer_type.value,
            "total": report.total,
            "verified": report.verified,
            "removed": report.removed_count,
            "needs_professional": answer.needs_professional,
        },
    )
    return answer


def _fallback_question(
    answer_type: AnswerType, suggested: str, checklist: Checklist | None
) -> str | None:
    """Give a not-found answer something the reader can still act on."""
    if answer_type is not AnswerType.NOT_FOUND:
        return suggested or None
    if suggested:
        return suggested
    if checklist and checklist.items:
        return checklist.items[0].question_to_ask
    return DEFAULT_QUESTION_TO_ASK
