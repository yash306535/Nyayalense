"""The one crossing from model output into domain results.

Everything a model returns passes through here, and everything that leaves here
has been verified. Keeping the conversion in a single module means there is one
place to look to confirm that no unverified statement can reach a result.
"""

from collections.abc import Sequence

from pydantic import ValidationError

from app.adapters.llm.schemas import LLMCitation, LLMStatement
from app.domain.models import Citation, Statement, VerificationReport
from app.domain.verification import ClauseIndex, verify_statements


def to_citation(citation: LLMCitation) -> Citation | None:
    """Convert a proposed citation, leaving it unverified.

    A model's citation carries no shape guarantee beyond its own loose schema
    -- ``clause_id`` is any string up to 64 characters, not necessarily one
    that looks like a real clause id. ``None`` when it does not even parse as
    one, so a malformed citation is dropped here, at the one place model
    output crosses into a result, rather than crashing the request over a
    shape nothing downstream was ever going to verify anyway.

    Args:
        citation: What the model proposed.

    Returns:
        The citation, or ``None`` when its own id could never address a real
        clause.
    """
    try:
        return Citation(clause_id=citation.clause_id, quote=citation.quote)
    except ValidationError:
        return None


def to_statement(statement: LLMStatement) -> Statement:
    """Convert a proposed statement, leaving every citation unverified."""
    citations = [to_citation(citation) for citation in statement.citations]
    return Statement(
        text=statement.text,
        kind=statement.kind,
        citations=[citation for citation in citations if citation is not None],
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
