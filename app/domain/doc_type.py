"""Guess what kind of document this is, from keywords alone.

Deciding between eight document types is a job for a lookup table, not a model
call: it is instant, free and explainable, and the user can always override it.
A model is consulted only when the keywords are genuinely inconclusive.
"""

import re
from dataclasses import dataclass
from typing import Final

from app.domain.enums import DocType, Role

#: Phrases that indicate a type, with the weight each carries. Longer, more
#: specific phrases score higher because a single generic word proves little.
_SIGNALS: Final[dict[DocType, dict[str, int]]] = {
    DocType.RENTAL_LEAVE_LICENCE: {
        "leave and licence": 6,
        "leave and license": 6,
        "licensee": 4,
        "licensor": 4,
        "tenant": 3,
        "landlord": 3,
        "security deposit": 3,
        "monthly rent": 3,
        "lock-in period": 2,
        "premises": 2,
        "भाडेकरार": 6,
        "किरायानामा": 6,
    },
    DocType.EMPLOYMENT_OFFER: {
        "offer of employment": 6,
        "offer letter": 6,
        "appointment letter": 6,
        "ctc": 4,
        "service bond": 4,
        "probation": 3,
        "notice period": 2,
        "relieving letter": 3,
        "joining date": 3,
        "designation": 2,
        "employee": 2,
    },
    DocType.LOAN_AGREEMENT: {
        "loan agreement": 6,
        "borrower": 4,
        "lender": 4,
        "emi": 4,
        "principal amount": 3,
        "rate of interest": 3,
        "prepayment": 3,
        "sanctioned": 2,
        "repayment schedule": 3,
        "default": 1,
    },
    DocType.INSURANCE_POLICY: {
        "insurance policy": 6,
        "policyholder": 4,
        "sum insured": 5,
        "premium": 3,
        "insurer": 3,
        "waiting period": 3,
        "pre-existing": 3,
        "claim settlement": 3,
        "exclusions": 2,
        "nominee": 2,
    },
    DocType.TERMS_OF_SERVICE: {
        "terms of service": 6,
        "terms of use": 6,
        "privacy policy": 4,
        "these terms": 3,
        "the platform": 2,
        "the service": 2,
        "user account": 3,
        "we may modify": 2,
        "governing law": 1,
    },
    DocType.NDA: {
        "non-disclosure": 6,
        "nondisclosure": 6,
        "confidential information": 5,
        "disclosing party": 4,
        "receiving party": 4,
        "trade secret": 3,
    },
    DocType.LEGAL_NOTICE: {
        "legal notice": 6,
        "notice under section": 5,
        "my client": 4,
        "through my client": 4,
        "within 15 days": 2,
        "hereby called upon": 4,
        "failing which": 3,
        "cause of action": 3,
        "advocate": 2,
    },
    DocType.GENERAL_CONTRACT: {
        "this agreement": 2,
        "party of the first part": 3,
        "witnesseth": 3,
        "in witness whereof": 2,
        "indemnify": 1,
    },
}

#: Roles offered first for each document type; the user can still pick another.
DEFAULT_ROLES: Final[dict[DocType, tuple[Role, ...]]] = {
    DocType.RENTAL_LEAVE_LICENCE: (Role.TENANT, Role.LANDLORD),
    DocType.EMPLOYMENT_OFFER: (Role.EMPLOYEE, Role.EMPLOYER),
    DocType.LOAN_AGREEMENT: (Role.BORROWER, Role.LENDER),
    DocType.INSURANCE_POLICY: (Role.POLICYHOLDER, Role.OTHER),
    DocType.TERMS_OF_SERVICE: (Role.CUSTOMER, Role.OTHER),
    DocType.NDA: (Role.OTHER,),
    DocType.LEGAL_NOTICE: (Role.NOTICE_RECIPIENT, Role.OTHER),
    DocType.GENERAL_CONTRACT: (Role.OTHER,),
}

#: Score below which the guess is not worth showing without a second opinion.
CONFIDENT_SCORE: Final = 8


@dataclass(frozen=True, slots=True)
class TypeGuess:
    """A document-type guess and how sure the rules are.

    Attributes:
        doc_type: The best-scoring type.
        confidence: 0.0-1.0, derived from the winning score and the runner-up.
        is_confident: Whether the caller can skip the model fallback.
        scores: Every type's score, so the reasoning can be shown or tested.
    """

    doc_type: DocType
    confidence: float
    is_confident: bool
    scores: dict[DocType, int]


def _score(text: str) -> dict[DocType, int]:
    """Score every document type against the text."""
    lowered = text.casefold()
    return {
        doc_type: sum(
            weight * len(re.findall(re.escape(phrase), lowered))
            for phrase, weight in signals.items()
        )
        for doc_type, signals in _SIGNALS.items()
    }


def guess_doc_type(text: str) -> TypeGuess:
    """Guess the document type from its text.

    Args:
        text: The document's full text. Only the opening is decisive in
            practice, but scoring everything costs little and is more robust.

    Returns:
        The best guess, its confidence, and every score.
    """
    scores = _score(text)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    best, best_score = ranked[0]
    runner_up_score = ranked[1][1] if len(ranked) > 1 else 0

    if best_score == 0:
        return TypeGuess(DocType.GENERAL_CONTRACT, 0.0, False, scores)

    margin = (best_score - runner_up_score) / best_score
    confidence = round(min(1.0, best_score / (CONFIDENT_SCORE * 2)) * (0.5 + margin / 2), 2)
    return TypeGuess(
        doc_type=best,
        confidence=confidence,
        is_confident=best_score >= CONFIDENT_SCORE and best_score > runner_up_score,
        scores=scores,
    )


def default_roles(doc_type: DocType) -> tuple[Role, ...]:
    """Return the roles to offer first for a document type."""
    return DEFAULT_ROLES.get(doc_type, (Role.OTHER,))
