"""What the offline provider returns for an overview and a review.

The two longest imitations, kept apart from the short ones. Each reads the
clauses the prompt carries and quotes their real text, so the verifier runs for
real rather than being bypassed.
"""

import re
from typing import Final

from app.adapters.llm.base import Prompt, PromptClause
from app.adapters.llm.fake import (
    MAX_STATEMENTS,
    mentions_ai,
    quote_from,
    rank_clauses,
    statement_from,
)
from app.adapters.llm.schemas import (
    LLMChecklistResult,
    LLMContradiction,
    LLMKeyDate,
    LLMKeyTerm,
    LLMModel,
    LLMObligation,
    LLMOverview,
    LLMParty,
    LLMReview,
    LLMRisk,
    LLMStatement,
)
from app.domain.enums import ChecklistStatus, ObligationOwner, Severity, StatementKind, TimingKind
from app.domain.verification import CLAUSES_PER_CONTRADICTION

#: How many risks the fake reports at most.
MAX_RISKS: Final = 5

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

#: Matches only the checklist lines the builder injects, not the instruction
#: bullets that surround them in the same prompt.
_CHECKLIST_ID_RE: Final = re.compile(
    r"^\s*-\s*item\s+(?P<id>[a-z0-9_]+):\s*(?P<text>.+)$", re.MULTILINE
)


def build_overview(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Summarise the document from the clauses it actually has.

    Args:
        prompt: The prompt, unused here: an overview asks no question.
        clauses: The clauses the prompt carries.

    Returns:
        An overview quoting only real clause text.
    """
    del prompt
    first = clauses[0] if clauses else None
    return LLMOverview(
        summary=_summary(first),
        parties=_parties(clauses),
        key_terms=_key_terms(clauses),
        obligations=_obligations(clauses),
        key_dates=_key_dates(clauses),
        injection_warning=mentions_ai(clauses),
    )


def _summary(first: PromptClause | None) -> list[LLMStatement]:
    """Open with one statement grounded in the document's first clause."""
    if first is None:
        return []
    return [
        statement_from(
            "This document sets out the terms the parties have agreed.",
            first,
            first.heading or first.text,
            StatementKind.INTERPRETATION,
        )
    ]


def _parties(clauses: tuple[PromptClause, ...]) -> list[LLMParty]:
    """Name the clauses that read like they introduce the parties."""
    ranked = rank_clauses(clauses, "between party parties licensor licensee employer")
    return [
        LLMParty(name=clause.heading or clause.id, described_as="named in the document")
        for clause, _ in ranked[:2]
    ]


def _key_terms(clauses: tuple[PromptClause, ...]) -> list[LLMKeyTerm]:
    """Offer a key term for each signal word a clause actually contains."""
    terms: list[LLMKeyTerm] = []
    for signal, (term_id, label) in _TERM_SIGNALS.items():
        ranked = rank_clauses(clauses, signal)
        if not ranked:
            continue
        clause = ranked[0][0]
        terms.append(
            LLMKeyTerm(
                id=term_id,
                label=label,
                value=quote_from(clause, signal)[:120],
                statements=[
                    statement_from(
                        f"{label} is set out here.", clause, signal, StatementKind.DIRECT
                    )
                ],
            )
        )
    return terms


def _obligations(clauses: tuple[PromptClause, ...]) -> list[LLMObligation]:
    """Report the clauses that read like they place a duty on the reader."""
    query = "shall pay must obligation responsible"
    return [
        LLMObligation(
            who=ObligationOwner.YOU,
            what=clause.heading or f"See clause {clause.label or clause.id}",
            timing_kind=TimingKind.UNSPECIFIED,
            statements=[
                statement_from(
                    "The document places this on you.", clause, query, StatementKind.INTERPRETATION
                )
            ],
        )
        for clause, _ in rank_clauses(clauses, query)[:MAX_STATEMENTS]
    ]


def _key_dates(clauses: tuple[PromptClause, ...]) -> list[LLMKeyDate]:
    """Report periods as relative, never as a calendar date it has not read."""
    query = "date day month year commencing from until"
    return [
        LLMKeyDate(
            title=clause.heading or "Date in the document",
            timing_kind=TimingKind.RELATIVE,
            description="The document describes this period in words.",
            statements=[
                statement_from(
                    "A period is set out here.", clause, "days months period", StatementKind.DIRECT
                )
            ],
        )
        for clause, _ in rank_clauses(clauses, query)[:2]
    ]


def build_review(prompt: Prompt, clauses: tuple[PromptClause, ...]) -> LLMModel:
    """Fill the checklist named in the instructions, then flag obvious risks.

    Args:
        prompt: The prompt, whose instructions carry the checklist items.
        clauses: The clauses the prompt carries.

    Returns:
        A review quoting only real clause text.
    """
    return LLMReview(
        checklist=_checklist(prompt.instructions, clauses),
        risks=_risks(clauses),
        contradictions=_contradictions(clauses),
        injection_warning=mentions_ai(clauses),
    )


def _checklist(instructions: str, clauses: tuple[PromptClause, ...]) -> list[LLMChecklistResult]:
    """Mark each curated item found or not found, by word overlap alone."""
    results: list[LLMChecklistResult] = []
    for item_id, text in _CHECKLIST_ID_RE.findall(instructions):
        ranked = rank_clauses(clauses, text)
        if ranked:
            results.append(
                LLMChecklistResult(
                    item_id=item_id,
                    status=ChecklistStatus.FOUND,
                    statements=[
                        statement_from(
                            "The document covers this.", ranked[0][0], text, StatementKind.DIRECT
                        )
                    ],
                )
            )
        else:
            results.append(
                LLMChecklistResult(
                    item_id=item_id,
                    status=ChecklistStatus.NOT_FOUND,
                    closest_clause_ids=[clause.id for clause in clauses[:1]],
                )
            )
    return results


def _risks(clauses: tuple[PromptClause, ...]) -> list[LLMRisk]:
    """Flag a risk for each signal word a clause actually contains."""
    risks: list[LLMRisk] = []
    for signal, title, severity in _RISK_SIGNALS:
        ranked = rank_clauses(clauses, signal)
        if not ranked:
            continue
        risks.append(
            LLMRisk(
                category="terms",
                title=title,
                severity=severity,
                explanation=f"{title}, according to the clause quoted here.",
                statements=[
                    statement_from(f"{title}.", ranked[0][0], signal, StatementKind.INTERPRETATION)
                ],
                question_to_ask="Can this be changed before I sign?",
            )
        )
    return risks[:MAX_RISKS]


def _contradictions(clauses: tuple[PromptClause, ...]) -> list[LLMContradiction]:
    """Report a notice-period conflict only when two clauses really disagree."""
    notice = [clause for clause, _ in rank_clauses(clauses, "notice period days terminate")]
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
                statement_from(
                    f"One clause sets {first_value} days.",
                    first,
                    "notice days",
                    StatementKind.DIRECT,
                ),
                statement_from(
                    f"Another sets {second_value} days.",
                    second,
                    "notice days",
                    StatementKind.DIRECT,
                ),
            ],
        )
    ]
