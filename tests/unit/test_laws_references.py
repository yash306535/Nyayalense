"""Parsing statutory citations in the forms people actually write them."""

import pytest
from app.domain.enums import LawAct
from app.domain.laws.references import find_references, parse_query


def acts_and_sections(text: str) -> list[str]:
    return [reference.display for reference in find_references(text)]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("IPC 420", "IPC 420"),
        ("420 IPC", "IPC 420"),
        ("I.P.C. 420", "IPC 420"),
        ("Section 420 of the Indian Penal Code", "IPC 420"),
        ("section 420 of the Penal Code", "IPC 420"),
        ("u/s 420 IPC", "IPC 420"),
        ("U/S 420 IPC", "IPC 420"),
        ("S. 420 IPC", "IPC 420"),
        ("Sec. 420 IPC", "IPC 420"),
        ("Indian Penal Code, Section 302", "IPC 302"),
    ],
    ids=lambda value: value if isinstance(value, str) else "",
)
def test_english_forms_of_an_ipc_reference(text: str, expected: str) -> None:
    assert expected in acts_and_sections(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("CrPC 438", "CRPC 438"),
        ("Cr.P.C. 154", "CRPC 154"),
        ("Section 154 of the Code of Criminal Procedure", "CRPC 154"),
        ("Criminal Procedure Code, section 41", "CRPC 41"),
        ("S. 65B Evidence Act", "IEA 65B"),
        ("Indian Evidence Act, 1872, section 65B", "IEA 65B"),
        ("BNS 318", "BNS 318"),
        ("Bharatiya Nyaya Sanhita, section 103", "BNS 103"),
        ("BNSS 173", "BNSS 173"),
        ("BSA 63", "BSA 63"),
    ],
)
def test_the_other_codes_are_recognised(text: str, expected: str) -> None:
    assert expected in acts_and_sections(text)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("धारा 420 भा.दं.सं.", "IPC 420"),
        ("भादंवि कलम 420", "IPC 420"),
        ("भारतीय दंड संहिता की धारा 420", "IPC 420"),
        ("भारतीय न्याय संहिता, 2023 की धारा 318", "BNS 318"),
        ("धारा ४२० भा.दं.सं.", "IPC 420"),
    ],
)
def test_hindi_and_marathi_forms(text: str, expected: str) -> None:
    assert expected in acts_and_sections(text)


def test_lettered_sections_keep_their_letter() -> None:
    assert acts_and_sections("section 498A IPC") == ["IPC 498A"]
    assert acts_and_sections("S. 65B Evidence Act") == ["IEA 65B"]


def test_a_subsection_is_kept_separately() -> None:
    reference = find_references("BNS 318(4)")[0]
    assert reference.section == "318"
    assert reference.subsection == "4"
    assert reference.display == "BNS 318(4)"


def test_a_list_of_sections_yields_each_one() -> None:
    assert acts_and_sections("under Sections 406 and 420 of the Indian Penal Code") == [
        "IPC 406",
        "IPC 420",
    ]


def test_a_comma_separated_list_yields_each_one() -> None:
    assert acts_and_sections("Sections 406, 420 and 506 IPC") == [
        "IPC 406",
        "IPC 420",
        "IPC 506",
    ]


def test_two_references_to_different_codes_are_both_found() -> None:
    assert acts_and_sections("Section 420 IPC and Section 154 CrPC") == ["IPC 420", "CRPC 154"]


def test_one_reference_found_by_two_patterns_appears_once() -> None:
    assert acts_and_sections("IPC 420") == ["IPC 420"]


# ---------------------------------------------------------------- false positives


@pytest.mark.parametrize(
    "text",
    [
        "on page 4 of the agreement",
        "clause 7.2 of this deed",
        "the Indian Penal Code, 1860",
        "the Code of Criminal Procedure, 1973",
        "paragraph 12 below",
        "Rs. 420 was paid",
        "the agreement dated 1 June 2025",
    ],
)
def test_ordinary_numbers_are_not_read_as_sections(text: str) -> None:
    assert find_references(text) == []


def test_the_evidence_act_year_decides_which_act_is_meant() -> None:
    assert acts_and_sections("Evidence Act 2023 section 63") == ["BSA 63"]
    assert acts_and_sections("Evidence Act, section 63") == ["IEA 63"]
    assert acts_and_sections("भारतीय साक्ष्य अधिनियम, 2023 की धारा 63") == ["BSA 63"]


# ---------------------------------------------------------------- reference shape


def test_a_reference_records_where_it_was_found() -> None:
    text = "Action was threatened under Section 420 of the Indian Penal Code today."
    reference = find_references(text)[0]
    assert text[reference.start : reference.end] == reference.raw
    assert reference.key == "ipc:420"


def test_old_and_new_acts_are_distinguished() -> None:
    assert find_references("IPC 420")[0].act.is_old
    assert not find_references("BNS 318")[0].act.is_old


@pytest.mark.parametrize("act", list(LawAct))
def test_every_act_is_reachable_from_its_abbreviation(act: LawAct) -> None:
    found = find_references(f"{act.value.upper()} 1")
    assert found and found[0].act is act


# ---------------------------------------------------------------- queries


def test_a_search_query_yields_one_reference() -> None:
    reference = parse_query("  s. 420 ipc  ")
    assert reference is not None
    assert reference.key == "ipc:420"


@pytest.mark.parametrize("query", ["", "hello", "420", "section 420"])
def test_a_query_naming_no_act_yields_nothing(query: str) -> None:
    assert parse_query(query) is None
