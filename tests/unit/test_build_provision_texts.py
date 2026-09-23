"""The provision-text readers, against the shapes the real sources take.

India Code publishes the two generations of code differently, so there are two
readers. Both are exercised here on fixtures cut to the patterns that actually
appear: a title that wraps across a line, a section number printed inside the
brackets an amendment left behind, a state legislature's variant printed under
the section it varies, and a heading with no space after its number.
"""

import pytest
from app.domain.enums import LawAct
from scripts.build_provision_texts import (
    MAX_TEXT_CHARS,
    SPECS,
    ActSpec,
    _sort_key,
    build,
    to_provision,
)
from scripts.indiacode import ExtractedSection
from scripts.indiacode.api import _get, _search_url, html_to_text, read_page
from scripts.indiacode.consolidated import (
    _heading_offset,
    _split_heading,
    listed_numbers,
    parse,
    reflow,
)
from scripts.indiacode.pages import Line, trim

# ---------------------------------------------------------------- the act PDFs


def line(text: str, weight: str = "", page: int = 1) -> Line:
    """Build a line, defaulting to all-roman text of the right length."""
    return Line(text=text, weight=weight or "." * len(text), page=page)


def bold(text: str, run: int, page: int = 1) -> Line:
    """Build a line whose first ``run`` characters are set in bold."""
    return Line(text=text, weight="B" * run + "." * (len(text) - run), page=page)


def test_trimming_a_line_keeps_its_weights_in_step() -> None:
    text, weight = trim("  420. Cheating.", "..BBBBBBBBBBBBBB")
    assert text == "420. Cheating."
    assert weight == "BBBBBBBBBBBBBB"
    assert len(weight) == len(text)


def test_a_bold_numbered_line_opens_a_section() -> None:
    assert _heading_offset(bold("420. Cheating.—Whoever cheats", 14)) == 0


def test_a_section_replaced_by_amendment_opens_after_its_bracket() -> None:
    # India Code prints a wholly substituted section inside square brackets, and
    # the bracket is not part of the heading.
    text = "[18. \u201cIndia\u201d.\u2014\u201cIndia\u201d means"
    assert _heading_offset(line(text)) is None
    weight = "." + "B" * 11 + "." * (len(text) - 12)
    assert _heading_offset(Line(text=text, weight=weight, page=1)) == 1


def test_a_line_that_is_not_bold_does_not_open_a_section() -> None:
    assert _heading_offset(line("420. is the section under which he was charged")) is None


def test_a_heading_with_no_space_after_its_number_still_opens_a_section() -> None:
    assert _heading_offset(bold("174A.Non-appearance.—Whoever fails", 20)) == 0


def test_a_title_keeps_the_full_stop_the_bold_run_left_behind() -> None:
    # The stop and the dash that close a title are sometimes set in roman.
    printed = "18. \u201cIndia\u201d.\u2014\u201cIndia\u201d means the territory"
    block = Line(text=printed, weight="B" * 11 + "." * (len(printed) - 11), page=1)
    number, title, text = _split_heading(block, 0)
    assert (number, title) == ("18", "“India”.")
    assert text.startswith("“India” means")


def test_a_repealed_section_is_reported_as_carrying_no_title() -> None:
    block = bold("15. [Definition of \u201cBritish India\u201d.] Rep. by the A. O. 1937.", 2)
    number, title, _ = _split_heading(block, 0)
    assert (number, title) == ("15", "")


def test_a_wrapped_title_is_rejoined_before_it_is_split() -> None:
    blocks = reflow(
        [
            bold("418. Cheating with knowledge that wrongful loss may", 51),
            bold("ensue to person whose interest.—Whoever cheats with", 31),
        ]
    )
    assert len(blocks) == 1
    number, title, text = _split_heading(blocks[0], 0)
    assert number == "418"
    assert title.endswith("whose interest.")
    assert text.startswith("Whoever cheats")


def test_a_numbered_paragraph_starts_a_new_line_of_its_own() -> None:
    blocks = reflow([line("shall be punished with fine."), line("(2) Whoever commits")])
    assert [block.text for block in blocks] == [
        "shall be punished with fine.",
        "(2) Whoever commits",
    ]


def act_lines() -> list[Line]:
    """A miniature act: front matter, two sections, and a state variant."""
    return [
        line("1. Short title."),
        line("2. Cheating."),
        line("3. Mischief."),
        line("WHEREAS it is expedient; It is enacted as follows:—"),
        bold("2. Cheating.—Whoever cheats is said to cheat.", 12),
        line("Explanation.—A concealment of facts is a deception."),
        line("STATE AMENDMENT Chhattisgarh After section 2, insert—"),
        bold("2A. Sextortion.—(1) Whoever abuses authority", 15),
        line("[Vide Chhattisgarh Act 25 of 2015, s. 3]"),
        bold("3. Mischief.—Whoever causes wrongful loss.", 12),
    ]


def test_the_arrangement_of_sections_lists_the_acts_own_numbers() -> None:
    assert listed_numbers(act_lines()) == frozenset({"1", "2", "3"})


def test_the_front_matter_is_not_read_as_sections() -> None:
    readout = parse(act_lines())
    assert [section.section for section in readout.sections] == ["2", "3"]


def test_a_state_variant_is_left_out_of_the_section_it_varies() -> None:
    readout = parse(act_lines())
    cheating = next(s for s in readout.sections if s.section == "2")
    assert "Sextortion" not in cheating.text
    assert "Chhattisgarh" not in cheating.text
    assert cheating.text.endswith("a deception.")


def test_a_section_only_a_state_inserted_is_not_packaged_as_the_acts_own() -> None:
    assert "2A" not in {section.section for section in parse(act_lines()).sections}


def test_a_number_printed_twice_keeps_the_first_and_says_so() -> None:
    lines = [
        line("1. One."),
        line("It is enacted as follows:—"),
        bold("1. One.—The first.", 7),
        bold("1. One again.—The second.", 13),
    ]
    readout = parse(lines)
    assert [s.text for s in readout.sections] == ["The first."]
    assert readout.repeated == ["1"]


def test_the_public_page_is_carried_onto_every_section() -> None:
    readout = parse(act_lines(), url="https://indiacode.gov.in/handle/123456789/488475")
    assert {s.url for s in readout.sections} == {"https://indiacode.gov.in/handle/123456789/488475"}


# ---------------------------------------------------------------- the API records


def test_published_markup_becomes_one_line_per_paragraph() -> None:
    markup = (
        '<span style="margin-left: 15px;"></span>(1) Whoever cheats.'
        '<br/><hr style="border: none;"/> <i>Explanation.</i>—A concealment.'
        "<br/><hr/> <i><center>Illustrations.</center></i><br/><hr/> (a) A cheats."
    )
    assert html_to_text(markup).split("\n") == [
        "(1) Whoever cheats.",
        "Explanation.—A concealment.",
        "Illustrations.",
        "(a) A cheats.",
    ]


def test_published_markup_keeps_its_entities() -> None:
    assert html_to_text("fine &amp; imprisonment &#8212; or both") == (
        "fine & imprisonment — or both"
    )


def test_empty_markup_yields_no_text() -> None:
    assert html_to_text('<span style="margin-left: 15px;"></span><br/>') == ""


def record(**metadata: str) -> dict[str, object]:
    """Build one search result in the shape DSpace returns."""
    return {
        "_embedded": {
            "indexableObject": {
                "handle": "123456789/545810",
                "name": metadata.get("dc.title", ""),
                "metadata": {key: [{"value": value}] for key, value in metadata.items()},
            }
        }
    }


def payload(*records: dict[str, object], pages: int = 1) -> dict[str, object]:
    """Wrap records in the envelope DSpace returns."""
    return {
        "_embedded": {
            "searchResult": {
                "_embedded": {"objects": list(records)},
                "page": {"totalPages": pages},
            }
        }
    }


def test_a_section_record_becomes_a_section() -> None:
    sections, skipped, pages = read_page(
        payload(
            record(
                **{
                    "dc.identifier.act_name": "The Bharatiya Nyaya Sanhita, 2023",
                    "dc.identifier.section_number": "318",
                    "dc.identifier.page_number": "93",
                    "dc.identifier.section_page_note": "(1) Whoever cheats.<br/>",
                    "dc.title": "Cheating.",
                }
            )
        ),
        "The Bharatiya Nyaya Sanhita, 2023",
    )
    assert (skipped, pages) == ([], 1)
    assert sections == [
        ExtractedSection(
            section="318",
            title="Cheating.",
            text="(1) Whoever cheats.",
            page=93,
            url="https://indiacode.gov.in/handle/123456789/545810",
        )
    ]


def test_a_record_from_another_act_is_left_out() -> None:
    sections, skipped, _ = read_page(
        payload(
            record(
                **{
                    "dc.identifier.act_name": "The Bharatiya Nagarik Suraksha Sanhita, 2023",
                    "dc.identifier.section_number": "318",
                    "dc.identifier.section_page_note": "Something else.",
                    "dc.title": "Elsewhere.",
                }
            )
        ),
        "The Bharatiya Nyaya Sanhita, 2023",
    )
    assert sections == []
    assert skipped == ["Elsewhere."]


def test_a_record_with_no_text_is_left_out_rather_than_filled_in() -> None:
    sections, skipped, _ = read_page(
        payload(
            record(
                **{
                    "dc.identifier.act_name": "The Bharatiya Nyaya Sanhita, 2023",
                    "dc.identifier.section_number": "318",
                    "dc.identifier.section_page_note": "",
                    "dc.title": "Cheating.",
                }
            )
        ),
        "The Bharatiya Nyaya Sanhita, 2023",
    )
    assert (sections, skipped) == ([], ["Cheating."])


def test_the_act_name_is_quoted_into_the_query() -> None:
    url = _search_url("The Bharatiya Nyaya Sanhita, 2023", page=2, size=100)
    assert "Bharatiya+Nyaya+Sanhita%2C+2023" in url
    assert url.startswith("https://indiacode.gov.in/server/api/discover/search/objects?")


def test_statutory_text_is_not_fetched_from_anywhere_but_india_code() -> None:
    with pytest.raises(ValueError, match="refusing to fetch"):
        _get("https://example.test/server/api/discover/search/objects")


# ---------------------------------------------------------------- packaging


SPEC = ActSpec(act=LawAct.IPC, url="https://indiacode.gov.in/handle/1", document="A PDF")


def test_a_section_becomes_a_row_marked_extracted() -> None:
    provision = to_provision(ExtractedSection("420", "Cheating.", "Whoever cheats.", 103), SPEC)
    assert provision is not None
    assert provision.key == "ipc:420"
    assert provision.review_status.value == "extracted"
    assert provision.verified_on is None
    assert provision.source.page == 103


def test_a_section_the_reader_could_not_title_is_left_out() -> None:
    assert to_provision(ExtractedSection("420", "", "Whoever cheats."), SPEC) is None


def test_a_section_longer_than_the_store_allows_is_left_out_not_cut_short() -> None:
    # Half a provision reads like the whole one, so it is not written at all.
    assert (
        to_provision(ExtractedSection("420", "Cheating.", "x" * (MAX_TEXT_CHARS + 1)), SPEC) is None
    )


def test_something_that_is_not_a_section_number_is_left_out() -> None:
    assert to_provision(ExtractedSection("Schedule I", "A schedule.", "Text."), SPEC) is None


def test_the_build_says_what_it_left_out() -> None:
    report = build(
        SPEC,
        [
            ExtractedSection("420", "Cheating.", "Whoever cheats."),
            ExtractedSection("421", "", "No title, so no row."),
        ],
    )
    assert [p.section for p in report.provisions] == ["420"]
    assert report.left_out == ["ipc 421: title 0 chars, text 20 chars"]


def test_sections_are_ordered_the_way_the_act_numbers_them() -> None:
    sections = [ExtractedSection(n, "T.", "x") for n in ("10", "2A", "2", "1")]
    assert [s.section for s in sorted(sections, key=_sort_key)] == ["1", "2", "2A", "10"]


def test_the_code_of_criminal_procedure_is_not_built() -> None:
    """Its only remaining copy is a gazette scan too degraded to quote from."""
    assert LawAct.CRPC not in {spec.act for spec in SPECS}
    assert {spec.act for spec in SPECS} == {
        LawAct.IPC,
        LawAct.IEA,
        LawAct.BNS,
        LawAct.BNSS,
        LawAct.BSA,
    }
