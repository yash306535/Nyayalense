"""The verifier is the product's central promise, so it is the most-tested file."""

import pytest
from app.domain.enums import RemovalReason, StatementKind
from app.domain.models import Citation, Clause, Document, Statement
from app.domain.verification import (
    EXACT_SCORE,
    ClauseIndex,
    both_sides_verified,
    merge_reports,
    unsupported_kinds,
    verify_citation,
    verify_statement,
    verify_statements,
)
from hypothesis import example, given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st

THRESHOLD = 92

CLAUSE_TEXT = (
    "The Licensee shall pay a security deposit of Rs. 60,000/- "
    "(Rupees Sixty Thousand only) before taking possession."
)


@pytest.fixture
def index(tiny_document: Document) -> ClauseIndex:
    return ClauseIndex(tiny_document)


def cite(clause_id: str, quote: str) -> Citation:
    return Citation(clause_id=clause_id, quote=quote)


# ---------------------------------------------------------------- citations


def test_exact_quote_verifies_with_a_perfect_score(index: ClauseIndex) -> None:
    outcome = verify_citation(
        cite("C1", "a security deposit of Rs. 60,000/-"), index, threshold=THRESHOLD
    )
    assert outcome.ok
    assert outcome.citation.verified
    assert outcome.citation.score == EXACT_SCORE


def test_verified_span_points_at_the_original_text(
    index: ClauseIndex, tiny_document: Document
) -> None:
    quote = "security deposit of Rs. 60,000/-"
    citation = verify_citation(cite("C1", quote), index, threshold=THRESHOLD).citation
    clause = tiny_document.clause("C1")
    assert clause is not None
    assert clause.text[citation.span_start : citation.span_end] == quote


@pytest.mark.parametrize(
    "quote",
    [
        "a  security   deposit  of  Rs. 60,000/-",
        "A SECURITY DEPOSIT OF RS. 60,000/-",
        "a security deposit of Rs. 60,000/–",
        "(Rupees Sixty Thousand only)",
        "a security deposit of Rs. 60,00O/-",
    ],
    ids=["whitespace", "case", "en-dash", "brackets", "ocr-noise"],
)
def test_close_quotes_still_verify(index: ClauseIndex, quote: str) -> None:
    assert verify_citation(cite("C1", quote), index, threshold=THRESHOLD).ok


def test_fabricated_quote_is_rejected(index: ClauseIndex) -> None:
    outcome = verify_citation(
        cite("C1", "pets are permitted in the premises at all times"), index, threshold=THRESHOLD
    )
    assert outcome.reason is RemovalReason.QUOTE_NOT_FOUND


def test_quote_attributed_to_the_wrong_clause_is_rejected(index: ClauseIndex) -> None:
    outcome = verify_citation(
        cite("C2", "a security deposit of Rs. 60,000/-"), index, threshold=THRESHOLD
    )
    assert outcome.reason is RemovalReason.QUOTE_NOT_FOUND


def test_unknown_clause_id_is_rejected(index: ClauseIndex) -> None:
    outcome = verify_citation(cite("C99", "anything at all here"), index, threshold=THRESHOLD)
    assert outcome.reason is RemovalReason.NO_SUCH_CLAUSE


def test_blank_quote_is_rejected(index: ClauseIndex) -> None:
    outcome = verify_citation(cite("C1", "   "), index, threshold=THRESHOLD)
    assert outcome.reason is RemovalReason.EMPTY_QUOTE


def test_quote_of_only_punctuation_is_rejected(index: ClauseIndex) -> None:
    outcome = verify_citation(cite("C1", "\u200b\u200b"), index, threshold=THRESHOLD)
    assert outcome.reason is RemovalReason.EMPTY_QUOTE


def test_over_long_quote_is_rejected(index: ClauseIndex) -> None:
    outcome = verify_citation(cite("C1", " ".join(["word"] * 41)), index, threshold=THRESHOLD)
    assert outcome.reason is RemovalReason.QUOTE_TOO_LONG


def test_a_short_quote_must_match_exactly(index: ClauseIndex) -> None:
    """A handful of characters fuzzy-matches anything, so exactness is required."""
    assert verify_citation(cite("C1", "deposit"), index, threshold=THRESHOLD).ok
    assert not verify_citation(cite("C1", "deposti"), index, threshold=THRESHOLD).ok


# ---------------------------------------------------------------- statements


def test_statement_keeps_only_the_citations_that_verified(index: ClauseIndex) -> None:
    result, reason = verify_statement(
        Statement(
            text="The deposit is 60000.",
            citations=[
                cite("C1", "a security deposit of Rs. 60,000/-"),
                cite("C1", "a clause that does not exist anywhere"),
            ],
        ),
        index,
        threshold=THRESHOLD,
    )
    assert reason is None
    assert result is not None
    assert len(result.citations) == 1


def test_statement_with_no_verifiable_citation_is_removed(index: ClauseIndex) -> None:
    result, reason = verify_statement(
        Statement(text="Pets are allowed.", citations=[cite("C1", "pets are allowed here always")]),
        index,
        threshold=THRESHOLD,
    )
    assert result is None
    assert reason is RemovalReason.NO_VERIFIED_CITATIONS


def test_statement_with_no_citations_at_all_is_removed(index: ClauseIndex) -> None:
    result, reason = verify_statement(
        Statement(text="Trust me.", citations=[]), index, threshold=THRESHOLD
    )
    assert result is None
    assert reason is RemovalReason.NO_VERIFIED_CITATIONS


# ---------------------------------------------------------------- figure check


def test_a_figure_the_quote_does_not_contain_removes_the_statement(index: ClauseIndex) -> None:
    result, reason = verify_statement(
        Statement(
            text="The deposit is 99000.",
            citations=[cite("C1", "a security deposit of Rs. 60,000/-")],
        ),
        index,
        threshold=THRESHOLD,
    )
    assert result is None
    assert reason is RemovalReason.FIGURE_NOT_IN_QUOTE


def test_digits_are_supported_by_the_same_amount_written_in_words(index: ClauseIndex) -> None:
    result, _ = verify_statement(
        Statement(
            text="The deposit is 60000.", citations=[cite("C1", "Rupees Sixty Thousand only")]
        ),
        index,
        threshold=THRESHOLD,
    )
    assert result is not None


def test_ordinary_number_words_in_prose_are_not_treated_as_figures(index: ClauseIndex) -> None:
    """An opening word such as 'One' is prose, not a figure."""
    result, _ = verify_statement(
        Statement(
            text="One clause sets 30 days.",
            citations=[cite("C2", "terminate this agreement on 30 days written notice")],
        ),
        index,
        threshold=THRESHOLD,
    )
    assert result is not None


def test_a_statement_with_no_figures_needs_no_figure_support(index: ClauseIndex) -> None:
    result, _ = verify_statement(
        Statement(
            text="Either side can end the agreement with notice.",
            citations=[cite("C2", "Either party may terminate this agreement")],
        ),
        index,
        threshold=THRESHOLD,
    )
    assert result is not None


def test_naming_the_cited_clauses_own_label_is_not_an_unsupported_figure(
    index: ClauseIndex,
) -> None:
    """C2's label is '9', which its own body text never repeats.

    A statement that names which clause it is quoting -- 'clause 9', 'IPC 376'
    -- is citing the source, not making a claim the source has to separately
    state. Without this, any statement naming its own clause number would be
    wrongly dropped whenever that clause does not also restate its number.
    """
    result, _ = verify_statement(
        Statement(
            text="Clause 9 lets either party end the agreement with notice.",
            citations=[cite("C2", "Either party may terminate this agreement")],
        ),
        index,
        threshold=THRESHOLD,
    )
    assert result is not None


def test_a_figure_matching_only_a_different_clauses_label_still_fails(
    index: ClauseIndex,
) -> None:
    """The label exemption is per citation, not a blanket pass for any digit
    that happens to label some other clause in the document.
    """
    result, reason = verify_statement(
        Statement(
            text="Clause 9 requires 500 days notice.",
            citations=[cite("C2", "Either party may terminate this agreement")],
        ),
        index,
        threshold=THRESHOLD,
    )
    assert result is None
    assert reason is RemovalReason.FIGURE_NOT_IN_QUOTE


def test_lettered_section_numbers_are_not_figures(index: ClauseIndex) -> None:
    """498A and 65B are labels, so neither side of the check produces a token."""
    result, _ = verify_statement(
        Statement(
            text="It refers to section 498A.",
            citations=[cite("C2", "Either party may terminate this agreement")],
        ),
        index,
        threshold=THRESHOLD,
    )
    assert result is not None


# ---------------------------------------------------------------- reports


def test_report_counts_and_explains_every_removal(index: ClauseIndex) -> None:
    kept, report = verify_statements(
        [
            Statement(text="Good.", citations=[cite("C1", "a security deposit of Rs. 60,000/-")]),
            Statement(text="Invented.", citations=[cite("C1", "pets are permitted on the roof")]),
            Statement(
                text="Wrong figure 12345.",
                citations=[cite("C1", "a security deposit of Rs. 60,000/-")],
            ),
        ],
        index,
        threshold=THRESHOLD,
    )
    assert len(kept) == 1
    assert report.total == 3
    assert report.verified == 1
    assert report.removed_count == 2
    assert not report.all_verified
    assert {entry.reason for entry in report.removed} == {
        RemovalReason.NO_VERIFIED_CITATIONS,
        RemovalReason.FIGURE_NOT_IN_QUOTE,
    }


def test_a_fully_verified_report_says_so(index: ClauseIndex) -> None:
    _, report = verify_statements(
        [Statement(text="Good.", citations=[cite("C1", "a security deposit of Rs. 60,000/-")])],
        index,
        threshold=THRESHOLD,
    )
    assert report.all_verified
    assert report.removed_count == 0


def test_merge_reports_sums_totals_and_keeps_every_removal(index: ClauseIndex) -> None:
    _, first = verify_statements(
        [Statement(text="Invented.", citations=[cite("C1", "pets on the roof are fine")])],
        index,
        threshold=THRESHOLD,
    )
    _, second = verify_statements(
        [Statement(text="Good.", citations=[cite("C1", "a security deposit of Rs. 60,000/-")])],
        index,
        threshold=THRESHOLD,
    )
    merged = merge_reports([first, second])
    assert merged.total == 2
    assert merged.verified == 1
    assert merged.removed_count == 1


def test_unsupported_kinds_reports_what_was_dropped(index: ClauseIndex) -> None:
    _, report = verify_statements(
        [
            Statement(
                text="Invented.",
                kind=StatementKind.INTERPRETATION,
                citations=[cite("C1", "pets on the roof are fine")],
            )
        ],
        index,
        threshold=THRESHOLD,
    )
    assert unsupported_kinds(report) == {StatementKind.INTERPRETATION}


def test_merge_of_no_reports_is_empty() -> None:
    merged = merge_reports([])
    assert merged.total == 0
    assert merged.all_verified


# ---------------------------------------------------------------- contradictions


def test_a_contradiction_needs_two_distinct_clauses() -> None:
    one_clause = Statement(
        text="Conflict.",
        citations=[
            Citation(clause_id="C1", quote="x", verified=True),
            Citation(clause_id="C1", quote="y", verified=True),
        ],
    )
    two_clauses = Statement(
        text="Conflict.",
        citations=[
            Citation(clause_id="C1", quote="x", verified=True),
            Citation(clause_id="C2", quote="y", verified=True),
        ],
    )
    assert not both_sides_verified(one_clause)
    assert both_sides_verified(two_clauses)


def test_an_unverified_side_does_not_count_towards_a_contradiction() -> None:
    statement = Statement(
        text="Conflict.",
        citations=[
            Citation(clause_id="C1", quote="x", verified=True),
            Citation(clause_id="C2", quote="y", verified=False),
        ],
    )
    assert not both_sides_verified(statement)


# ---------------------------------------------------------------- index


def test_normalised_clause_text_is_computed_once(tiny_document: Document) -> None:
    index = ClauseIndex(tiny_document)
    assert index.normalized("C1") is index.normalized("C1")


def test_index_returns_nothing_for_an_unknown_clause(tiny_document: Document) -> None:
    index = ClauseIndex(tiny_document)
    assert index.clause("C99") is None
    assert index.normalized("C99") is None
    assert index.numeric_values("C99") == frozenset()


# ---------------------------------------------------------------- properties


def _clause(text: str) -> ClauseIndex:
    return ClauseIndex(
        Document(id="p", doc_type="general_contract", clauses=[Clause(id="C1", text=text)])
    )


@given(start=st.integers(min_value=0, max_value=60), length=st.integers(min_value=15, max_value=50))
@hypothesis_settings(max_examples=60)
def test_any_substring_of_a_clause_verifies(start: int, length: int) -> None:
    index = _clause(CLAUSE_TEXT)
    quote = CLAUSE_TEXT[start : start + length]
    if len(quote) < 15:
        return
    assert verify_citation(cite("C1", quote), index, threshold=THRESHOLD).ok


@given(
    start=st.integers(min_value=0, max_value=60),
    length=st.integers(min_value=20, max_value=50),
    spaces=st.integers(min_value=1, max_value=4),
)
@hypothesis_settings(max_examples=60)
def test_a_substring_survives_whitespace_and_quote_damage(
    start: int, length: int, spaces: int
) -> None:
    index = _clause(CLAUSE_TEXT)
    quote = CLAUSE_TEXT[start : start + length]
    if len(quote) < 20:
        return
    damaged = quote.replace(" ", " " * spaces).replace("'", "’").replace("-", "–")
    assert verify_citation(cite("C1", damaged), index, threshold=THRESHOLD).ok


@given(
    st.text(alphabet=st.characters(min_codepoint=97, max_codepoint=122), min_size=25, max_size=60)
)
@example("the licensee shall never pay anything at all under this agreement ever")
@hypothesis_settings(max_examples=60)
def test_text_that_is_not_in_the_clause_never_verifies(invented: str) -> None:
    index = _clause(CLAUSE_TEXT)
    if invented.casefold() in CLAUSE_TEXT.casefold():
        return
    assert not verify_citation(cite("C1", invented), index, threshold=THRESHOLD).ok
