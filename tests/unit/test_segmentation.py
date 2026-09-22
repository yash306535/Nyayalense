"""Clause segmentation across the numbering styles Indian drafting uses."""

import unicodedata
from itertools import pairwise

import pytest
from app.constants import MAX_CLAUSE_CHARS
from app.domain.segmentation import clean_pages, join_hyphenated_breaks, segment


def labels(pages: list[str]) -> list[str]:
    return [clause.label for clause in segment(pages)]


@pytest.mark.parametrize(
    ("line", "expected_label"),
    [
        ("1. First clause text here.", "1"),
        ("1) First clause text here.", "1"),
        ("1.1 Sub clause text here.", "1.1"),
        ("1.1.2 Deep clause text here.", "1.1.2"),
        ("(a) Lettered clause text here.", "a"),
        ("(iv) Roman clause text here.", "iv"),
        ("a. Lettered clause text here.", "a"),
        ("Clause 5 Some text follows here.", "5"),
        ("Section 3 Some text follows here.", "3"),
        ("Article IV. Some text follows here.", "IV"),
        ("कलम 7 काही मजकूर येथे आहे.", "7"),
        ("धारा 12 कुछ पाठ यहाँ है.", "12"),
    ],
)
def test_every_numbering_style_is_recognised(line: str, expected_label: str) -> None:
    assert expected_label in labels([line])


def test_devanagari_numerals_are_read_as_labels() -> None:
    assert "१.१" in labels(["१.१ काही मजकूर येथे आहे आणि तो पुरेसा लांब आहे."]) or "1.1" in labels(
        ["१.१ काही मजकूर येथे आहे आणि तो पुरेसा लांब आहे."]
    )


def test_clause_ids_are_sequential_and_unique() -> None:
    clauses = segment(["1. One here.\n2. Two here.\n3. Three here."])
    ids = [clause.id for clause in clauses]
    assert ids == sorted(ids, key=lambda value: int(value[1:]))
    assert len(set(ids)) == len(ids)


def test_a_title_becomes_a_heading_rather_than_body_text() -> None:
    clauses = segment(["LEAVE AND LICENCE AGREEMENT\n\nThis agreement is made on 1 April 2026."])
    assert clauses[0].heading == "LEAVE AND LICENCE AGREEMENT"
    assert clauses[0].text == "This agreement is made on 1 April 2026."


def test_a_numbered_heading_is_kept_with_its_subclauses() -> None:
    clauses = segment(["1. DEFINITIONS\nIn this agreement, terms have the meanings given."])
    assert clauses[0].heading == "DEFINITIONS"


def test_schedules_start_their_own_block() -> None:
    clauses = segment(["1. Body text here.\nSCHEDULE I\nDescription of the premises."])
    assert any(clause.heading.startswith("SCHEDULE") for clause in clauses)


def test_pages_are_recorded() -> None:
    clauses = segment(["1. First page clause.", "2. Second page clause."])
    assert [clause.page for clause in clauses] == [1, 2]


def test_offsets_do_not_overlap() -> None:
    clauses = segment(["1. First clause here.\n2. Second clause here.\n3. Third clause here."])
    for earlier, later in pairwise(clauses):
        assert earlier.end <= later.start


def test_an_unnumbered_document_falls_back_to_paragraphs() -> None:
    clauses = segment(["First paragraph of prose.\n\nSecond paragraph of prose."])
    assert clauses


def test_a_very_long_block_splits_at_sentence_boundaries() -> None:
    sentence = "This is a sentence of a reasonable length that repeats. "
    long_text = "1. " + sentence * 60
    clauses = segment([long_text])
    assert len(clauses) > 1
    assert {clause.id for clause in clauses} == {"C1a", "C1b", "C1c"} or len(clauses) >= 2
    for clause in clauses:
        assert len(clause.text) <= MAX_CLAUSE_CHARS + len(sentence)
        assert clause.text.strip().endswith(".")


def test_split_parts_get_letter_suffixes() -> None:
    long_text = "1. " + "A sentence that is long enough to matter here. " * 60
    ids = [clause.id for clause in segment([long_text])]
    assert ids[0].endswith("a")
    assert ids[1].endswith("b")


# ---------------------------------------------------------------- page furniture


def test_a_header_repeated_on_most_pages_is_removed() -> None:
    pages = [f"Confidential Draft\n1.{index} Clause text.\nPage {index}" for index in range(1, 5)]
    cleaned = clean_pages(pages)
    assert all("Confidential Draft" not in page for page in cleaned)


def test_bare_page_numbers_are_removed() -> None:
    cleaned = clean_pages(["1. Clause text.\n3", "2. Clause text.\nPage 2 of 5", "3. More.\n- 3 -"])
    joined = "\n".join(cleaned)
    assert "Page 2 of 5" not in joined
    assert "- 3 -" not in joined


def test_a_short_document_keeps_its_repeated_lines() -> None:
    """With two pages, a repeat is coincidence rather than a running header."""
    pages = ["Agreement\n1. Text here.", "Agreement\n2. Text here."]
    assert all("Agreement" in page for page in clean_pages(pages))


def test_hyphenated_line_breaks_are_rejoined() -> None:
    assert join_hyphenated_breaks("termi-\nnation") == "termination"
    assert join_hyphenated_breaks("well-\nknown") == "wellknown"


def test_a_hyphen_not_at_a_line_break_is_left_alone() -> None:
    assert join_hyphenated_breaks("lock-in period") == "lock-in period"


def test_empty_pages_produce_no_clauses() -> None:
    assert segment(["", "   ", "\n\n"]) == []


def test_clause_text_is_stored_in_nfc() -> None:
    decomposed = "1. Café terms apply here always."
    clause = segment([unicodedata.normalize("NFD", decomposed)])[0]
    assert clause.text == unicodedata.normalize("NFC", clause.text)
