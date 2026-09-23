"""What the offline provider returns for each task.

Each builder reads the clauses the prompt carries and quotes their real text, so
the verifier, the highlighting and every export are exercised rather than
bypassed. A builder that finds no overlap says so instead of inventing an answer.
"""

import re
from collections.abc import Callable
from typing import Final

from app.adapters.llm.base import Prompt, PromptClause, Task, parse_document_block
from app.adapters.llm.fake import (
    MAX_STATEMENTS,
    mentions_ai,
    quote_from,
    rank_clauses,
    statement_from,
)
from app.adapters.llm.fake_analysis import build_overview, build_review
from app.adapters.llm.schemas import (
    LLMAnswer,
    LLMChangeExplanation,
    LLMCompare,
    LLMDocTypeGuess,
    LLMModel,
    LLMScenario,
    LLMWording,
)
from app.domain.enums import (
    AnswerType,
    DocType,
    Severity,
    StatementKind,
)


def build_qa(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Answer a question, or admit the document does not cover it."""
    ranked = rank_clauses(clauses, prompt.question)
    if not ranked:
        return LLMAnswer(
            answer_type=AnswerType.NOT_FOUND,
            suggested_question_to_other_party=("Could you confirm this in writing before I sign?"),
            related_clause_ids=[clause.id for clause in clauses[:2]],
            injection_warning=mentions_ai(clauses),
        )
    # The statement text must not name the clause label: a label such as "7.3"
    # reads as a figure, and the figure check would rightly reject it because no
    # quote contains that number.
    return LLMAnswer(
        answer_type=AnswerType.DIRECT,
        statements=[
            statement_from(
                f"The document says: {quote_from(clause, prompt.question)}",
                clause,
                prompt.question,
                StatementKind.DIRECT,
            )
            for clause, _ in ranked[:MAX_STATEMENTS]
        ],
        related_clause_ids=[clause.id for clause, _ in ranked[:MAX_STATEMENTS]],
        injection_warning=mentions_ai(clauses),
    )


def _build_scenario(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Say what the document itself covers about a situation."""
    ranked = rank_clauses(clauses, prompt.instructions + " " + prompt.question)
    return LLMScenario(
        says=[
            statement_from(
                "The document deals with this here.",
                clause,
                prompt.instructions,
                StatementKind.DIRECT,
            )
            for clause, _ in ranked[:2]
        ],
        not_covered=[] if ranked else ["This document does not describe that situation."],
        next_steps=["Ask the other party to confirm this in writing."],
    )


def _build_compare(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Explain each changed clause pair listed in the instructions."""
    del clauses
    labels = re.findall(r"^\s*-\s*Clause\s+(?P<label>\S+)", prompt.instructions, re.MULTILINE)
    pairs = parse_document_block(prompt.document)
    by_label = {clause.label: clause for clause in pairs}
    return LLMCompare(
        changes=[
            LLMChangeExplanation(
                clause_label=label,
                statements=[
                    statement_from(
                        "The wording of this clause changed between the two versions.",
                        by_label[label],
                        label,
                        StatementKind.DIRECT,
                    )
                ],
                impact="Check this clause closely before you agree to it.",
                severity=Severity.MEDIUM,
            )
            for label in labels
            if label in by_label
        ]
    )


def _build_law_change(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Describe the difference between the stored OLD and NEW provision texts."""
    del prompt
    return LLMAnswer(
        answer_type=AnswerType.DIRECT if clauses else AnswerType.NOT_FOUND,
        statements=[
            statement_from(
                "The wording of the provision differs between the two codes.",
                clause,
                clause.text,
                StatementKind.DIRECT,
            )
            for clause in clauses[:2]
        ],
    )


def _build_doc_type(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Guess the document type from the words the document uses."""
    del prompt
    haystack = " ".join(clause.text for clause in clauses).casefold()
    for needle, doc_type in (
        ("licence", DocType.RENTAL_LEAVE_LICENCE),
        ("employment", DocType.EMPLOYMENT_OFFER),
        ("loan", DocType.LOAN_AGREEMENT),
        ("policy", DocType.INSURANCE_POLICY),
        ("notice", DocType.LEGAL_NOTICE),
    ):
        if needle in haystack:
            return LLMDocTypeGuess(doc_type=doc_type, confidence=0.5)
    return LLMDocTypeGuess(doc_type=DocType.GENERAL_CONTRACT, confidence=0.3)


def _build_wording(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Return template-style wording that uses the required slots correctly."""
    del clauses
    required = re.findall(r"\[\[([a-z0-9_]+)\]\]", prompt.instructions)
    slots = required or ["details"]
    body = " ".join(f"I refer to [[{slot}]]." for slot in dict.fromkeys(slots))
    return LLMWording(
        text=(
            "I am writing about the matter set out below. "
            f"{body} I would be grateful for your response."
        ),
        slots_used=list(dict.fromkeys(slots)),
    )


BUILDERS: Final[dict[Task, Callable[[Prompt, tuple[PromptClause, ...]], LLMModel]]] = {
    Task.QA: build_qa,
    Task.OVERVIEW: build_overview,
    Task.REVIEW: build_review,
    Task.SCENARIO: _build_scenario,
    Task.COMPARE: _build_compare,
    Task.LAW_CHANGE: _build_law_change,
    Task.DOC_TYPE: _build_doc_type,
    Task.WORDING: _build_wording,
}

if set(BUILDERS) != set(Task):  # pragma: no cover - guards against an unhandled task
    missing = ", ".join(sorted(task.value for task in set(Task) - set(BUILDERS)))
    raise RuntimeError(f"the fake provider has no builder for: {missing}")

__all__ = ["BUILDERS"]
