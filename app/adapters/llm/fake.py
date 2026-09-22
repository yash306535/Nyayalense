"""A deterministic, document-aware language model.

Demo mode has to be honest, not merely silent: a fake that returned canned
prose would let unverifiable text through and hide exactly the bug the verifier
exists to catch. So this provider only ever quotes text that is really in the
document, picking clauses by word overlap with the task. Every quote it returns
verifies, every answer it cannot support comes back as ``not_found``, and the
browser tests exercise the real pipeline end to end with no network and no key.
"""

import re
import time
from collections.abc import Callable
from typing import Final

from app.adapters.llm.base import (
    LLMResult,
    LLMUsage,
    Prompt,
    PromptClause,
    ResponseT,
    Task,
    parse_document_block,
)
from app.adapters.llm.schemas import (
    LLMAnswer,
    LLMChangeExplanation,
    LLMChecklistResult,
    LLMCitation,
    LLMCompare,
    LLMContradiction,
    LLMDocTypeGuess,
    LLMKeyDate,
    LLMKeyTerm,
    LLMModel,
    LLMObligation,
    LLMOverview,
    LLMParty,
    LLMReview,
    LLMRisk,
    LLMScenario,
    LLMStatement,
    LLMWording,
)
from app.constants import MAX_QUOTE_WORDS
from app.domain.enums import (
    AnswerType,
    ChecklistStatus,
    DocType,
    ObligationOwner,
    Severity,
    StatementKind,
    TimingKind,
)
from app.domain.verification import CLAUSES_PER_CONTRADICTION

_WORD_RE: Final = re.compile(r"[\wऀ-ॿ]+")

_STOPWORDS: Final[frozenset[str]] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does",
    "for", "from", "has", "have", "how", "if", "in", "is", "it", "its", "may", "me",
    "my", "not", "of", "on", "or", "shall", "should", "that", "the", "their", "there",
    "these", "this", "to", "was", "what", "when", "where", "which", "who", "will",
    "with", "would", "you", "your",
})  # fmt: skip

#: Shorter words carry too little meaning to rank a clause on.
MIN_WORD_LENGTH: Final = 3

#: Terms an overview looks for, and the key-term id each produces.
_TERM_SIGNALS: Final[dict[str, tuple[str, str]]] = {
    "deposit": ("deposit", "Security deposit"),
    "rent": ("rent", "Rent"),
    "salary": ("salary", "Salary"),
    "ctc": ("ctc", "Total pay"),
    "notice": ("notice_period", "Notice period"),
    "lock-in": ("lock_in", "Lock-in period"),
    "terminate": ("termination", "Termination"),
    "interest": ("interest", "Interest rate"),
    "premium": ("premium", "Premium"),
    "bond": ("bond", "Service bond"),
    "penalty": ("penalty", "Penalty"),
}

_RISK_SIGNALS: Final[tuple[tuple[str, str, Severity], ...]] = (
    ("forfeit", "Deposit can be forfeited", Severity.HIGH),
    ("lock-in", "You are locked in for a fixed period", Severity.HIGH),
    ("bond", "You are bound to stay for a fixed period", Severity.HIGH),
    ("penalty", "A penalty applies", Severity.MEDIUM),
    ("terminate", "The other side can end this early", Severity.MEDIUM),
    ("increase", "Amounts can go up", Severity.MEDIUM),
    ("indemnify", "You take on the other side's losses", Severity.MEDIUM),
)

_CHECKLIST_ID_RE: Final = re.compile(r"^\s*-\s*(?P<id>[a-z0-9_]+):\s*(?P<text>.+)$", re.MULTILINE)

MIN_OVERLAP: Final = 1
MAX_STATEMENTS: Final = 3


def _words(text: str) -> set[str]:
    """Split text into meaningful lowercase words."""
    return {
        word.casefold()
        for word in _WORD_RE.findall(text)
        if len(word) >= MIN_WORD_LENGTH and word.casefold() not in _STOPWORDS
    }


def _rank(clauses: tuple[PromptClause, ...], query: str) -> list[tuple[PromptClause, int]]:
    """Rank clauses by how many query words they contain, best first."""
    wanted = _words(query)
    scored = [
        (clause, len(wanted & _words(f"{clause.heading} {clause.text}"))) for clause in clauses
    ]
    return sorted(
        (entry for entry in scored if entry[1] >= MIN_OVERLAP),
        key=lambda entry: (-entry[1], entry[0].id),
    )


def _quote(clause: PromptClause, query: str) -> str:
    """Take the most relevant real sentence from a clause, within the word cap."""
    wanted = _words(query)
    sentences = [
        piece.strip() for piece in re.split(r"(?<=[.;।])\s+", clause.text) if piece.strip()
    ]
    best = max(sentences, key=lambda s: (len(wanted & _words(s)), -len(s)), default=clause.text)
    words = best.split()
    return " ".join(words[:MAX_QUOTE_WORDS])


def _statement(text: str, clause: PromptClause, query: str, kind: StatementKind) -> LLMStatement:
    """Build one statement quoting a clause that really contains the words."""
    return LLMStatement(
        text=text,
        kind=kind,
        citations=[LLMCitation(clause_id=clause.id, quote=_quote(clause, query))],
    )


def _mentions_ai(clauses: tuple[PromptClause, ...]) -> bool:
    """Detect text inside the document that addresses an AI system."""
    haystack = " ".join(clause.text for clause in clauses).casefold()
    return any(
        marker in haystack
        for marker in ("ai assistant", "ai system", "language model", "chatbot", "ai reviewing")
    )


class FakeLLMClient:
    """Offline provider used by tests, ``make dev-fake`` and demo deployments."""

    async def generate(
        self, prompt: Prompt, schema: type[ResponseT], *, task: Task
    ) -> LLMResult[ResponseT]:
        """Produce a schema-valid response grounded in the prompt's own document.

        Args:
            prompt: The prompt that would have gone to a real model.
            schema: The shape the caller expects back.
            task: Which analysis to imitate.

        Returns:
            The parsed response and a usage record marked as the fake model.
        """
        started = time.perf_counter()
        clauses = prompt.clauses or parse_document_block(prompt.document)
        payload = _BUILDERS[task](prompt, clauses)
        return LLMResult(
            data=schema.model_validate(payload.model_dump()),
            usage=LLMUsage(
                prompt_tokens=len(prompt.as_text()) // 4,
                output_tokens=len(payload.model_dump_json()) // 4,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                model="fake",
            ),
        )


def _build_qa(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Answer a question, or admit the document does not cover it."""
    ranked = _rank(clauses, prompt.question)
    if not ranked:
        return LLMAnswer(
            answer_type=AnswerType.NOT_FOUND,
            suggested_question_to_other_party=("Could you confirm this in writing before I sign?"),
            related_clause_ids=[clause.id for clause in clauses[:2]],
            injection_warning=_mentions_ai(clauses),
        )
    # The statement text must not name the clause label: a label such as "7.3"
    # reads as a figure, and the figure check would rightly reject it because no
    # quote contains that number.
    return LLMAnswer(
        answer_type=AnswerType.DIRECT,
        statements=[
            _statement(
                f"The document says: {_quote(clause, prompt.question)}",
                clause,
                prompt.question,
                StatementKind.DIRECT,
            )
            for clause, _ in ranked[:MAX_STATEMENTS]
        ],
        related_clause_ids=[clause.id for clause, _ in ranked[:MAX_STATEMENTS]],
        injection_warning=_mentions_ai(clauses),
    )


def _build_overview(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Summarise the document from the clauses it actually has."""
    del prompt
    first = clauses[0] if clauses else None
    key_terms = [
        LLMKeyTerm(
            id=term_id,
            label=label,
            value=_quote(ranked[0][0], signal)[:120],
            statements=[
                _statement(f"{label} is set out here.", ranked[0][0], signal, StatementKind.DIRECT)
            ],
        )
        for signal, (term_id, label) in _TERM_SIGNALS.items()
        if (ranked := _rank(clauses, signal))
    ]
    dates = _rank(clauses, "date day month year commencing from until")
    return LLMOverview(
        summary=(
            [
                _statement(
                    "This document sets out the terms the parties have agreed.",
                    first,
                    first.heading or first.text,
                    StatementKind.INTERPRETATION,
                )
            ]
            if first
            else []
        ),
        parties=[
            LLMParty(name=party.heading or party.id, described_as="named in the document")
            for party, _ in _rank(clauses, "between party parties licensor licensee employer")[:2]
        ],
        key_terms=key_terms,
        obligations=[
            LLMObligation(
                who=ObligationOwner.YOU,
                what=clause.heading or f"See clause {clause.label or clause.id}",
                timing_kind=TimingKind.UNSPECIFIED,
                statements=[
                    _statement(
                        "The document places this on you.",
                        clause,
                        "shall pay must",
                        StatementKind.INTERPRETATION,
                    )
                ],
            )
            for clause, _ in _rank(clauses, "shall pay must obligation responsible")[
                :MAX_STATEMENTS
            ]
        ],
        key_dates=[
            LLMKeyDate(
                title=clause.heading or "Date in the document",
                timing_kind=TimingKind.RELATIVE,
                description="The document describes this period in words.",
                statements=[
                    _statement(
                        "A period is set out here.",
                        clause,
                        "days months period",
                        StatementKind.DIRECT,
                    )
                ],
            )
            for clause, _ in dates[:2]
        ],
        injection_warning=_mentions_ai(clauses),
    )


def _build_review(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Fill the checklist named in the instructions, then flag obvious risks."""
    items = _CHECKLIST_ID_RE.findall(prompt.instructions)
    checklist: list[LLMChecklistResult] = []
    for item_id, text in items:
        ranked = _rank(clauses, text)
        if ranked:
            checklist.append(
                LLMChecklistResult(
                    item_id=item_id,
                    status=ChecklistStatus.FOUND,
                    statements=[
                        _statement(
                            "The document covers this.", ranked[0][0], text, StatementKind.DIRECT
                        )
                    ],
                )
            )
        else:
            checklist.append(
                LLMChecklistResult(
                    item_id=item_id,
                    status=ChecklistStatus.NOT_FOUND,
                    closest_clause_ids=[clause.id for clause in clauses[:1]],
                )
            )

    risks = [
        LLMRisk(
            category="terms",
            title=title,
            severity=severity,
            explanation=f"{title}, according to the clause quoted here.",
            statements=[
                _statement(f"{title}.", ranked[0][0], signal, StatementKind.INTERPRETATION)
            ],
            question_to_ask="Can this be changed before I sign?",
        )
        for signal, title, severity in _RISK_SIGNALS
        if (ranked := _rank(clauses, signal))
    ]
    return LLMReview(
        checklist=checklist,
        risks=risks[:5],
        contradictions=_contradictions(clauses),
        injection_warning=_mentions_ai(clauses),
    )


def _contradictions(clauses: tuple[PromptClause, ...]) -> list[LLMContradiction]:
    """Report a notice-period conflict only when two clauses really disagree."""
    notice = [clause for clause, _ in _rank(clauses, "notice period days terminate")]
    numbers = [
        (clause, re.findall(r"\b(\d{1,3})\s*(?:days|day)\b", clause.text, re.I))
        for clause in notice
    ]
    found = [(clause, values[0]) for clause, values in numbers if values]
    if len({value for _, value in found}) < CLAUSES_PER_CONTRADICTION:
        return []
    (first, first_value), (second, second_value) = found[0], found[1]
    return [
        LLMContradiction(
            title="Two different notice periods",
            explanation=(
                f"One clause says {first_value} days and another says {second_value} days."
            ),
            statements=[
                _statement(
                    f"One clause sets {first_value} days.",
                    first,
                    "notice days",
                    StatementKind.DIRECT,
                ),
                _statement(
                    f"Another sets {second_value} days.",
                    second,
                    "notice days",
                    StatementKind.DIRECT,
                ),
            ],
        )
    ]


def _build_scenario(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Say what the document itself covers about a situation."""
    ranked = _rank(clauses, prompt.instructions + " " + prompt.question)
    return LLMScenario(
        says=[
            _statement(
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
                    _statement(
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
            _statement(
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


_BUILDERS: Final[dict[Task, Callable[[Prompt, tuple[PromptClause, ...]], LLMModel]]] = {
    Task.QA: _build_qa,
    Task.OVERVIEW: _build_overview,
    Task.REVIEW: _build_review,
    Task.SCENARIO: _build_scenario,
    Task.COMPARE: _build_compare,
    Task.LAW_CHANGE: _build_law_change,
    Task.DOC_TYPE: _build_doc_type,
    Task.WORDING: _build_wording,
}

if set(_BUILDERS) != set(Task):  # pragma: no cover - guards against an unhandled task
    missing = ", ".join(sorted(task.value for task in set(Task) - set(_BUILDERS)))
    raise RuntimeError(f"the fake provider has no builder for: {missing}")

__all__ = ["FakeLLMClient"]
