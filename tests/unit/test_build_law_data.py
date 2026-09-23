"""The law-data build script, against small extracted-row fixtures.

The real BPR&D tables are laid out inconsistently with each other (the IEA
table puts the old section first; the other two put the new section first),
and cite provisos and explanations alongside plain section numbers. These
fixtures exercise both layouts and the rows that do not parse.
"""

import pytest
from app.domain.enums import ChangeType, LawAct, ReviewStatus
from scripts.build_law_data import (
    KNOWN_NOT_CARRIED_FORWARD,
    SPECS,
    RawRow,
    TransitionSpec,
    _combined_note,
    _group_by_old_section,
    _known_gaps,
    _rows_from_table,
    _section_number,
    build_transition,
    classify,
)

SPEC: TransitionSpec = SPECS[0]  # ipc_bns, new_first
IEA_SPEC: TransitionSpec = next(spec for spec in SPECS if spec.column_order == "old_first")


def raw(**overrides: object) -> RawRow:
    return RawRow(
        **{
            "old_section": "420",
            "new_section": "318",
            "title": "Cheating",
            "note": "",
            "page": 7,
            **overrides,
        }
    )


# ---------------------------------------------------------------- section parsing


@pytest.mark.parametrize(
    ("cell", "expected"),
    [
        ("318", "318"),
        ("108A", "108A"),
        ("103 (1)", "103"),
        ("65B", "65B"),
        ("New", None),
        ("-", None),
        ("", None),
        ("First proviso to section 22", None),
    ],
)
def test_a_section_cell_is_parsed_or_recognised_as_not_one(cell: str, expected: str | None) -> None:
    assert _section_number(cell) == expected


# ---------------------------------------------------------------- table layouts


def test_a_new_first_table_reads_new_title_old_note_in_that_order() -> None:
    """This is the IPC and CrPC table layout."""
    table = [["318", "Cheating.", "420", "No change."]]
    rows, skipped = _rows_from_table(table, page=32, column_order="new_first")
    assert skipped == 0
    assert rows == [
        RawRow(old_section="420", new_section="318", title="Cheating.", note="No change.", page=32)
    ]


def test_an_old_first_table_reads_old_new_title_note_in_that_order() -> None:
    """This is the IEA table layout."""
    table = [["4", "6", "Relevancy of facts.", "No change."]]
    rows, skipped = _rows_from_table(table, page=2, column_order="old_first")
    assert skipped == 0
    assert rows[0].old_section == "4"
    assert rows[0].new_section == "6"


def test_a_row_naming_no_old_counterpart_is_skipped() -> None:
    table = [["47", "A definition.", "New", "This is new."]]
    rows, skipped = _rows_from_table(table, page=1, column_order="new_first")
    assert rows == []
    assert skipped == 1


def test_a_row_citing_a_proviso_instead_of_a_section_is_skipped() -> None:
    table = [["First proviso to section 22", "28", "A heading.", "Note."]]
    rows, skipped = _rows_from_table(table, page=5, column_order="old_first")
    assert rows == []
    assert skipped == 1


def test_a_short_row_is_skipped_without_crashing() -> None:
    rows, skipped = _rows_from_table([["318", "Cheating"]], page=1, column_order="new_first")
    assert rows == []
    assert skipped == 0


def test_newlines_inside_a_cell_are_flattened() -> None:
    table = [["318", "Cheating and\ndishonestly inducing", "420", "No\nchange."]]
    rows, _ = _rows_from_table(table, page=1, column_order="new_first")
    assert "\n" not in rows[0].title
    assert "\n" not in rows[0].note


# ---------------------------------------------------------------- grouping


def test_rows_sharing_an_old_section_are_grouped_into_one() -> None:
    """A section split across subsections that map differently, like 498A."""
    grouped = _group_by_old_section(
        [raw(old_section="498A", new_section="85"), raw(old_section="498A", new_section="86")]
    )
    assert len(grouped) == 1
    assert sorted(grouped[0].new_sections) == ["85", "86"]


def test_distinct_old_sections_stay_separate() -> None:
    grouped = _group_by_old_section([raw(old_section="420"), raw(old_section="406")])
    assert {row.old_section for row in grouped} == {"420", "406"}


def test_duplicate_notes_are_not_repeated() -> None:
    grouped = _group_by_old_section(
        [raw(note="No change."), raw(note="No change."), raw(note="Word added.")]
    )
    assert grouped[0].notes.count("No change.") == 1


def test_no_change_notes_are_dropped_from_the_combined_note() -> None:
    grouped = _group_by_old_section([raw(note="No change.")])
    assert _combined_note(grouped[0]) == ""


def test_a_substantive_note_survives_combination() -> None:
    grouped = _group_by_old_section([raw(note="The word 'coercion' is added.")])
    assert "coercion" in _combined_note(grouped[0])


# ---------------------------------------------------------------- classification


def test_one_new_section_and_no_note_is_renumbered() -> None:
    grouped = _group_by_old_section([raw()])[0]
    assert classify(grouped, "") is ChangeType.RENUMBERED


def test_a_substantive_note_makes_it_modified() -> None:
    grouped = _group_by_old_section([raw()])[0]
    assert classify(grouped, "Wording changed.") is ChangeType.MODIFIED


def test_two_new_sections_is_a_split() -> None:
    grouped = _group_by_old_section([raw(new_section="85"), raw(new_section="86")])[0]
    assert classify(grouped, "") is ChangeType.SPLIT


def test_a_merge_note_is_recognised_even_with_one_new_section() -> None:
    grouped = _group_by_old_section([raw()])[0]
    assert classify(grouped, "Sections merged together.") is ChangeType.MERGED


# ---------------------------------------------------------------- building


def test_every_built_row_carries_its_source_page() -> None:
    transition = build_transition(SPEC, [raw(page=7), raw(old_section="406", page=9)])
    pages = {
        m.source.page
        for m in transition.mappings
        if m.change_type != ChangeType.NO_DIRECT_EQUIVALENT
    }
    assert pages == {7, 9}
    for mapping in transition.mappings:
        assert "BPR&D" in mapping.source.document or "Publicly reported" in mapping.source.document


def test_every_built_row_starts_unreviewed() -> None:
    """Nothing reaches a user until a person has checked it."""
    transition = build_transition(SPEC, [raw()])
    for mapping in transition.mappings:
        assert mapping.review_status is ReviewStatus.EXTRACTED
        assert mapping.verified_on is None
        assert not mapping.is_reviewed


def test_the_transition_names_both_acts_and_the_commencement_date() -> None:
    transition = build_transition(SPEC, [raw()])
    assert transition.old_act is LawAct.IPC
    assert transition.new_act is LawAct.BNS
    assert transition.in_force_from == "2024-07-01"
    assert "not a statutory instrument" in transition.source_note


def test_the_script_covers_all_three_transitions() -> None:
    assert {spec.id for spec in SPECS} == {"ipc_bns", "crpc_bnss", "iea_bsa"}


def test_building_from_no_rows_still_carries_the_known_gaps() -> None:
    transition = build_transition(SPEC, [])
    assert len(transition.mappings) == len(KNOWN_NOT_CARRIED_FORWARD["ipc_bns"])


# ---------------------------------------------------------------- known gaps


def test_known_gaps_are_marked_no_direct_equivalent_and_unreviewed() -> None:
    gaps = _known_gaps(SPEC)
    assert gaps, "the ipc_bns transition should have at least one recorded gap"
    for gap in gaps:
        assert gap.change_type is ChangeType.NO_DIRECT_EQUIVALENT
        assert gap.new == []
        assert gap.review_status is ReviewStatus.EXTRACTED
        assert gap.note


def test_sedition_is_among_the_known_gaps() -> None:
    sections = {section for section, _ in KNOWN_NOT_CARRIED_FORWARD["ipc_bns"]}
    assert "124A" in sections


def test_a_transition_with_no_recorded_gaps_adds_none() -> None:
    assert _known_gaps(IEA_SPEC) == []
