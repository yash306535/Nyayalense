"""Citation verification: the one place a model's claims are checked.

Nothing reaches the user on the model's word. Every quote is matched against the
clause it claims to come from, every figure is matched against those quotes, and
whatever fails is removed and counted. The functions here are pure and
deterministic, which is why the guarantee is testable rather than aspirational.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from rapidfuzz import fuzz

from app.domain.amounts import digit_values, numeric_values
from app.domain.enums import RemovalReason, StatementKind
from app.domain.models import (
    Citation,
    Clause,
    Document,
    RemovedStatement,
    Statement,
    VerificationReport,
)
from app.domain.normalize import NormalizedText, normalize, normalize_with_map

#: An exact substring match needs no fuzzy score.
EXACT_SCORE: Final = 100

#: Below this many characters a fuzzy match is meaningless, so require exactness.
MIN_FUZZY_QUOTE_CHARS: Final = 12

#: A contradiction is a claim about two places at once, so it needs two clauses.
CLAUSES_PER_CONTRADICTION: Final = 2


@dataclass(frozen=True, slots=True)
class CitationOutcome:
    """What verification made of one citation."""

    citation: Citation
    reason: RemovalReason | None = None

    @property
    def ok(self) -> bool:
        """True when the citation verified."""
        return self.reason is None


class ClauseIndex:
    """Clause lookup with normalised text computed once per document.

    Verification touches the same clauses repeatedly across an overview, a
    review and several questions. Normalising on every lookup would dominate the
    cost, so each clause is normalised the first time it is used and kept.
    """

    def __init__(self, document: Document) -> None:
        """Build an index over a document's clauses.

        Args:
            document: The document whose clauses citations may refer to.
        """
        self._clauses = document.by_id
        self._normalized: dict[str, NormalizedText] = {}

    def clause(self, clause_id: str) -> Clause | None:
        """Return the clause with this id, or ``None``."""
        return self._clauses.get(clause_id)

    def normalized(self, clause_id: str) -> NormalizedText | None:
        """Return the normalised form of a clause, with its offset map."""
        if clause_id not in self._clauses:
            return None
        cached = self._normalized.get(clause_id)
        if cached is None:
            cached = normalize_with_map(self._clauses[clause_id].text)
            self._normalized[clause_id] = cached
        return cached

    def numeric_values(self, clause_id: str) -> frozenset[Decimal]:
        """Return every number in a clause, in any spelling."""
        clause = self._clauses.get(clause_id)
        return numeric_values(clause.text) if clause else frozenset()


def verify_citation(citation: Citation, index: ClauseIndex, *, threshold: int) -> CitationOutcome:
    """Check one quote against the clause it claims to come from.

    Args:
        citation: The citation as the model returned it.
        index: Clause lookup for the document under analysis.
        threshold: Minimum partial ratio, 0-100, for a fuzzy match to count.

    Returns:
        The citation with verification fields filled in, or a rejection reason.
    """
    if not citation.quote.strip():
        return CitationOutcome(citation, RemovalReason.EMPTY_QUOTE)
    if citation.is_too_long:
        return CitationOutcome(citation, RemovalReason.QUOTE_TOO_LONG)

    haystack = index.normalized(citation.clause_id)
    if haystack is None:
        return CitationOutcome(citation, RemovalReason.NO_SUCH_CLAUSE)

    needle = normalize(citation.quote)
    if not needle:
        return CitationOutcome(citation, RemovalReason.EMPTY_QUOTE)

    match = _locate(needle, haystack, threshold=threshold)
    if match is None:
        return CitationOutcome(citation, RemovalReason.QUOTE_NOT_FOUND)

    score, start, end = match
    span_start, span_end = haystack.to_source_span(start, end)
    return CitationOutcome(
        citation.model_copy(
            update={
                "verified": True,
                "score": score,
                "span_start": span_start,
                "span_end": span_end,
            }
        )
    )


def _locate(
    needle: str, haystack: NormalizedText, *, threshold: int
) -> tuple[int, int, int] | None:
    """Find ``needle`` in ``haystack``, exactly or closely enough.

    Args:
        needle: Normalised quote.
        haystack: Normalised clause text with its offset map.
        threshold: Minimum partial ratio for a fuzzy match.

    Returns:
        ``(score, start, end)`` in normalised coordinates, or ``None``.
    """
    exact = haystack.text.find(needle)
    if exact >= 0:
        return (EXACT_SCORE, exact, exact + len(needle))

    # A short quote that is not an exact substring is more likely invented than
    # mistyped, and fuzzy matching a handful of characters finds anything.
    if len(needle) < MIN_FUZZY_QUOTE_CHARS:
        return None

    alignment = fuzz.partial_ratio_alignment(needle, haystack.text, score_cutoff=threshold)
    if alignment is None:
        return None
    return (int(alignment.score), alignment.dest_start, alignment.dest_end)


def verify_statement(
    statement: Statement, index: ClauseIndex, *, threshold: int
) -> tuple[Statement | None, RemovalReason | None]:
    """Verify one statement's citations, then its figures.

    Args:
        statement: The statement as the model returned it.
        index: Clause lookup for the document under analysis.
        threshold: Minimum partial ratio for a fuzzy quote match.

    Returns:
        The statement with only verified citations, or ``None`` and the reason
        it was dropped.
    """
    verified = [
        outcome.citation
        for outcome in (
            verify_citation(citation, index, threshold=threshold)
            for citation in statement.citations
        )
        if outcome.ok
    ]
    if not verified:
        return (None, RemovalReason.NO_VERIFIED_CITATIONS)

    if not _figures_are_supported(statement.text, verified, index):
        return (None, RemovalReason.FIGURE_NOT_IN_QUOTE)

    return (statement.model_copy(update={"citations": verified}), None)


def _figures_are_supported(text: str, citations: list[Citation], index: ClauseIndex) -> bool:
    """Check that every figure in ``text`` appears in one of the quotes.

    The two sides are treated differently on purpose. A claim is checked on its
    digits only, because the prompt contract requires explanations to write
    numbers as digits and an ordinary word such as "one" is not a figure. The
    evidence side counts both spellings, so a claim of ``60000`` is supported by
    a clause that says "Sixty Thousand".

    A cited clause's own label counts as supported too, on the same logic: when
    a statement names which clause it comes from -- "clause 7.2", "IPC 376" --
    that number identifies the citation itself rather than claiming something
    the clause's text has to separately state. Without this, a statement would
    be dropped for citing the very clause it is quoting, whenever that clause
    does not also repeat its own number in its body.

    A quote is checked against its whole source clause rather than the quoted
    span, because normalisation and the model's own trimming both move the
    boundaries a little. The clause is still the evidence the user is shown.

    Args:
        text: The statement's explanation.
        citations: Citations that already verified.
        index: Clause lookup for the document under analysis.

    Returns:
        True when the statement mentions no figure the evidence does not contain.
    """
    claimed = digit_values(text)
    if not claimed:
        return True
    supported: set[Decimal] = set()
    for citation in citations:
        supported |= numeric_values(citation.quote)
        supported |= index.numeric_values(citation.clause_id)
        clause = index.clause(citation.clause_id)
        if clause is not None and clause.label:
            supported |= numeric_values(clause.label)
    return claimed <= supported


def verify_statements(
    statements: list[Statement], index: ClauseIndex, *, threshold: int
) -> tuple[list[Statement], VerificationReport]:
    """Verify a list of statements and report what happened.

    Args:
        statements: Statements as the model returned them.
        index: Clause lookup for the document under analysis.
        threshold: Minimum partial ratio for a fuzzy quote match.

    Returns:
        The surviving statements and a report of the totals and removals.
    """
    kept: list[Statement] = []
    removed: list[RemovedStatement] = []

    for statement in statements:
        result, reason = verify_statement(statement, index, threshold=threshold)
        if result is None:
            removed.append(
                RemovedStatement(
                    reason=reason or RemovalReason.NO_VERIFIED_CITATIONS, kind=statement.kind
                )
            )
        else:
            kept.append(result)

    return kept, VerificationReport(total=len(statements), verified=len(kept), removed=removed)


def merge_reports(reports: list[VerificationReport]) -> VerificationReport:
    """Combine several reports into the one figure shown on a result.

    Args:
        reports: Reports from each part of a composite result.

    Returns:
        A single report summing totals and concatenating removals.
    """
    removed: list[RemovedStatement] = []
    for report in reports:
        removed.extend(report.removed)
    return VerificationReport(
        total=sum(report.total for report in reports),
        verified=sum(report.verified for report in reports),
        removed=removed,
    )


def both_sides_verified(statement: Statement) -> bool:
    """Check that a claimed contradiction cites two different clauses.

    A contradiction is a claim about two places at once. One verified quote does
    not support it, so a single-clause contradiction is dropped.

    Args:
        statement: A statement describing a contradiction.

    Returns:
        True when at least two distinct clauses back the statement.
    """
    cited = {citation.clause_id for citation in statement.citations if citation.verified}
    return len(cited) >= CLAUSES_PER_CONTRADICTION


def unsupported_kinds(report: VerificationReport) -> set[StatementKind]:
    """Return the kinds of statement that were removed, for disclosure copy."""
    return {entry.kind for entry in report.removed}
