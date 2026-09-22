"""The law-data build script, against small extracted-row fixtures."""

import pytest
from app.domain.enums import ChangeType, LawAct, ReviewStatus
from scripts.build_law_data import (
    SPECS,
    Row,
    TransitionSpec,
    _parse_sections,
    _rows_from_table,
    build_transition,
    classify,
)

SPEC: TransitionSpec = SPECS[0]


def row(**overrides: object) -> Row:
    return Row(
        **{
            "old_section": "420",
            "old_title": "Cheating",
            "new_sections": ("318",),
            "new_title": "Cheating",
            "note": "",
            "page": 7,
            **overrides,
        }
    )


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("318", ("318",)),
        ("85 and 86", ("85", "86")),
        ("103, 104", ("103", "104")),
        ("65B", ("65B",)),
        ("Omitted", ()),
        ("No corresponding provision", ()),
        ("—", ()),
        ("", ()),
    ],
)
def test_the_new_section_cell_is_parsed(cell: str, expected: tuple[str, ...]) -> None:
    assert _parse_sections(cell) == expected


@pytest.mark.parametrize(
    ("entry", "expected"),
    [
        (row(), ChangeType.RENUMBERED),
        (row(new_sections=("85", "86")), ChangeType.SPLIT),
        (row(new_sections=()), ChangeType.NO_DIRECT_EQUIVALENT),
        (row(note="Merged with section 316"), ChangeType.MERGED),
        (row(note="Modified wording"), ChangeType.MODIFIED),
        (row(note="Amended in the new code"), ChangeType.MODIFIED),
    ],
)
def test_rows_are_classified_from_their_own_shape(entry: Row, expected: ChangeType) -> None:
    """Classification is arithmetic on the cells, never a view about the law."""
    assert classify(entry) is expected


def test_a_table_row_is_extracted_with_its_page() -> None:
    table = [["420", "Cheating", "318", "Cheating", "Merged"]]
    extracted = _rows_from_table(table, page=12)
    assert len(extracted) == 1
    assert extracted[0].old_section == "420"
    assert extracted[0].page == 12


def test_a_header_row_is_skipped() -> None:
    table = [["IPC", "Description", "BNS", "Description"], ["420", "Cheating", "318", "Cheating"]]
    assert [entry.old_section for entry in _rows_from_table(table, page=1)] == ["420"]


def test_a_row_with_too_few_columns_is_skipped() -> None:
    assert _rows_from_table([["420", "Cheating"]], page=1) == []


def test_a_row_whose_first_cell_is_not_a_section_is_skipped() -> None:
    assert _rows_from_table([["see below", "x", "y"]], page=1) == []


def test_newlines_inside_a_cell_are_flattened() -> None:
    extracted = _rows_from_table(
        [["420", "Cheating and\ndishonestly inducing", "318", "x"]], page=1
    )
    assert "\n" not in extracted[0].old_title


def test_every_built_row_carries_its_source_page() -> None:
    transition = build_transition(SPEC, [row(page=7), row(old_section="406", page=9)])
    pages = {mapping.source.page for mapping in transition.mappings}
    assert pages == {7, 9}
    for mapping in transition.mappings:
        assert "BPR&D" in mapping.source.document


def test_every_built_row_starts_unreviewed() -> None:
    """Nothing reaches a user until a person has checked it."""
    transition = build_transition(SPEC, [row()])
    for mapping in transition.mappings:
        assert mapping.review_status is ReviewStatus.EXTRACTED
        assert mapping.verified_on is None
        assert not mapping.is_reviewed


def test_duplicate_old_sections_are_collapsed() -> None:
    transition = build_transition(SPEC, [row(page=1), row(page=2)])
    assert len(transition.mappings) == 1
    assert transition.mappings[0].source.page == 1


def test_the_transition_names_both_acts_and_the_commencement_date() -> None:
    transition = build_transition(SPEC, [row()])
    assert transition.old_act is LawAct.IPC
    assert transition.new_act is LawAct.BNS
    assert transition.in_force_from == "2024-07-01"
    assert "not a statutory instrument" in transition.source_note


def test_the_script_covers_all_three_transitions() -> None:
    assert {spec.id for spec in SPECS} == {"ipc_bns", "crpc_bnss", "iea_bsa"}


def test_building_from_no_rows_produces_an_empty_transition() -> None:
    assert build_transition(SPEC, []).mappings == []
