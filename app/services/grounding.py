"""The one crossing from model output into domain results.

Everything a model returns passes through here, and everything that leaves here
has been verified. Keeping the conversion in a single module means there is one
place to look to confirm that no unverified statement can reach a result.
"""

from collections.abc import Sequence

from app.adapters.llm.schemas import LLMCitation, LLMStatement
from app.domain.models import Citation, Statement, VerificationReport
from app.domain.verification import ClauseIndex, verify_statements


def to_citation(citation: LLMCitation) -> Citation:
    """Convert a proposed citation, leaving it unverified."""
    return Citation(clause_id=citation.clause_id, quote=citation.quote)


def to_statement(statement: LLMStatement) -> Statement:
    """Convert a proposed statement, leaving every citation unverified."""
    return Statement(
        text=statement.text,
        kind=statement.kind,
        citations=[to_citation(citation) for citation in statement.citations],
    )


def ground(
    statements: Sequence[LLMStatement], index: ClauseIndex, *, threshold: int
) -> tuple[list[Statement], VerificationReport]:
    """Verify proposed statements against the document.

    Args:
        statements: What the model returned.
        index: Clause lookup for the document under analysis.
        threshold: Minimum partial ratio for a fuzzy quote match.

    Returns:
        The statements that survived, and a report of what was removed.
    """
    return verify_statements(
        [to_statement(statement) for statement in statements], index, threshold=threshold
    )
