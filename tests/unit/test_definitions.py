"""Extracting the terms a document defines for itself."""

from app.domain.definitions import extract_defined_terms
from app.domain.models import Clause


def terms(*texts: str) -> dict[str, str]:
    clauses = [Clause(id=f"C{index}", text=text) for index, text in enumerate(texts, start=1)]
    return {entry.term: entry.definition for entry in extract_defined_terms(clauses)}


def test_a_quoted_definition_is_found() -> None:
    found = terms('In this agreement, "Premises" means Flat 7B, Sunrise Residency.')
    assert found["Premises"] == "Flat 7B, Sunrise Residency"


def test_two_definitions_in_one_clause_are_both_found() -> None:
    found = terms('"Premises" means Flat 7B. "Term" shall mean twelve months.')
    assert set(found) == {"Premises", "Term"}
    assert found["Term"] == "twelve months"


def test_a_hereinafter_label_takes_the_name_before_it() -> None:
    found = terms(
        'This deed is between Mr. A. Kulkarni of Pune (hereinafter referred to as the "Licensor").'
    )
    assert "Kulkarni" in found["Licensor"]


def test_hereinafter_called_is_recognised_too() -> None:
    assert "Licensee" in terms('Ms. B. Rao of Mumbai (hereinafter called the "Licensee").')


def test_an_unquoted_definition_line_is_found() -> None:
    found = terms("Lock-in Period means the first eleven months of the Term.")
    assert found["Lock-in Period"] == "the first eleven months of the Term"


def test_an_abbreviation_does_not_end_the_definition() -> None:
    found = terms('"Fee" means the sum of Rs. 5,000 payable monthly. Something else follows.')
    assert found["Fee"] == "the sum of Rs. 5,000 payable monthly"


def test_the_first_definition_of_a_term_wins() -> None:
    found = terms('"Term" means twelve months.', '"Term" means twenty four months.')
    assert found["Term"] == "twelve months"


def test_the_clause_a_term_was_defined_in_is_recorded() -> None:
    clauses = [
        Clause(id="C1", text="Nothing here."),
        Clause(id="C2", text='"Premises" means Flat 7B.'),
    ]
    assert extract_defined_terms(clauses)[0].clause_id == "C2"


def test_a_document_with_no_definitions_yields_none() -> None:
    assert terms("The licence fee is payable monthly.") == {}


def test_a_very_long_definition_is_trimmed() -> None:
    body = "the arrangement described at length " * 12
    found = terms(f'"Thing" means {body.strip()}.')
    assert len(found["Thing"]) <= 300
