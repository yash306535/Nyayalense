"""The one crossing from model output into a result.

A model's own citation schema is deliberately loose -- an id is any string up
to 64 characters, because it is unverified until checked. This is what makes
sure a citation shaped nothing like a real clause id is dropped here rather
than crashing the whole request.
"""

from app.adapters.llm.schemas import LLMCitation, LLMStatement
from app.domain.enums import StatementKind
from app.services.grounding import to_citation, to_statement


def test_a_well_formed_citation_converts() -> None:
    citation = to_citation(LLMCitation(clause_id="C1", quote="the deposit is refundable"))
    assert citation is not None
    assert citation.clause_id == "C1"
    assert citation.verified is False


def test_a_citation_id_that_is_not_a_real_shape_is_dropped_not_raised() -> None:
    """A model sometimes echoes back a whole header line instead of an id.

    ``"IPC-497 | IPC 497 | p.114 | Adultery."`` is not a shape any real clause
    id takes -- a bare identifier never contains a pipe or a space -- so this
    must come back ``None`` rather than raise past the boundary meant to catch
    exactly this.
    """
    citation = to_citation(
        LLMCitation(clause_id="IPC-497 | IPC 497 | p.114 | Adultery.", quote="whoever")
    )
    assert citation is None


def test_a_statement_with_one_malformed_citation_keeps_its_other_citations() -> None:
    statement = to_statement(
        LLMStatement(
            text="Cheating is defined here.",
            kind=StatementKind.DIRECT,
            citations=[
                LLMCitation(clause_id="C1", quote="a real quote"),
                LLMCitation(clause_id="not a real id [with brackets]", quote="a bad one"),
            ],
        )
    )
    assert [citation.clause_id for citation in statement.citations] == ["C1"]


def test_a_statement_with_only_malformed_citations_has_none_left() -> None:
    statement = to_statement(
        LLMStatement(
            text="Cheating is defined here.",
            kind=StatementKind.DIRECT,
            citations=[LLMCitation(clause_id="not a real id [with brackets]", quote="bad")],
        )
    )
    assert statement.citations == []
