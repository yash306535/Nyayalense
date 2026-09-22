"""The three renderers, and the one model they all read."""

import io

import pdfplumber
import pytest
from app.domain.document_model import (
    Block,
    BlockType,
    DocumentModel,
    bullets,
    heading,
    paragraph,
    quote,
    table,
)
from app.errors import ExportError
from app.rendering import docx as docx_renderer
from app.rendering import pdf as pdf_renderer
from app.rendering.html import render as render_html
from app.rendering.markdown import parse
from docx import Document as WordDocument

MARKDOWN = """# Request to refund the deposit

To: **Mr. Anil Deshpande**

I am writing about the deposit of 60,000 paid on 2026-05-01.

- The agreement ended.
- The keys were handed back.

> Clause 4.1: the deposit is refundable.

| Item | Amount |
| --- | --- |
| Deposit | 60,000 |
"""


# ---------------------------------------------------------------- markdown


def test_every_block_kind_is_parsed() -> None:
    model = parse(MARKDOWN, title="Letter")
    kinds = [block.type for block in model.blocks]
    assert BlockType.HEADING in kinds
    assert BlockType.PARAGRAPH in kinds
    assert BlockType.LIST in kinds
    assert BlockType.QUOTE in kinds
    assert BlockType.TABLE in kinds


def test_a_heading_keeps_its_level() -> None:
    model = parse("### Third level")
    assert model.blocks[0].level == 3


def test_a_heading_deeper_than_four_is_clamped() -> None:
    assert parse("###### Sixth level").blocks[0].level == 4


def test_bold_and_italic_become_runs() -> None:
    runs = parse("Plain **bold** and *italic*.").blocks[0].runs
    assert any(run.bold for run in runs)
    assert any(run.italic for run in runs)


def test_a_table_has_a_header_row() -> None:
    block = next(b for b in parse(MARKDOWN).blocks if b.type is BlockType.TABLE)
    assert any(cell.header for cell in block.rows[0])
    assert block.rows[1][1].text == "60,000"


def test_an_ordered_list_is_marked_ordered() -> None:
    block = parse("1. one\n2. two").blocks[0]
    assert block.ordered
    assert block.items == ["one", "two"]


def test_a_rule_is_parsed() -> None:
    assert parse("---").blocks[0].type is BlockType.RULE


def test_confirmed_facts_are_marked_in_the_runs() -> None:
    model = parse(MARKDOWN, facts={"60,000", "Mr. Anil Deshpande"})
    marked = {run.text for block in model.blocks for run in block.runs if run.fact}
    assert marked == {"60,000", "Mr. Anil Deshpande"}


def test_a_fact_that_is_not_present_marks_nothing() -> None:
    model = parse("Nothing to see here.", facts={"99,999"})
    assert not any(run.fact for block in model.blocks for run in block.runs)


def test_html_in_the_source_stays_text_and_never_becomes_markup() -> None:
    """The parser has HTML disabled, so a tag is characters, not structure."""
    model = parse("<script>alert(1)</script>\n\nNormal text.")
    assert all(block.type is BlockType.PARAGRAPH for block in model.blocks)
    assert "<script>alert(1)</script>" in model.text

    html = render_html(model, inline_css=False)
    assert "<script>alert" not in html
    assert "&lt;script&gt;" in html


def test_the_model_exposes_its_plain_text() -> None:
    model = parse(MARKDOWN)
    assert "60,000" in model.text
    assert "The keys were handed back." in model.text


# ---------------------------------------------------------------- html


def test_html_escapes_every_piece_of_text() -> None:
    model = DocumentModel(title="T", blocks=[paragraph("<script>alert(1)</script>")])
    html = render_html(model, inline_css=False)
    assert "&lt;script&gt;" in html
    assert "<script>alert" not in html


def test_html_escapes_the_title_too() -> None:
    model = DocumentModel(title='"><script>x</script>', blocks=[])
    assert "<script>" not in render_html(model, inline_css=False)


def test_html_escapes_list_items_and_table_cells() -> None:
    model = DocumentModel(
        title="T",
        blocks=[bullets(["<b>item</b>"]), table([["<th>", "x"], ["<td>", "y"]])],
    )
    html = render_html(model, inline_css=False)
    assert "<b>item</b>" not in html
    assert "&lt;b&gt;item&lt;/b&gt;" in html


def test_html_carries_the_language_for_assistive_technology() -> None:
    model = DocumentModel(title="T", language="hi", blocks=[])
    assert 'lang="hi"' in render_html(model, inline_css=False)


def test_html_renders_a_real_table_header() -> None:
    model = DocumentModel(title="T", blocks=[table([["A", "B"], ["1", "2"]])])
    html = render_html(model, inline_css=False)
    assert "<thead>" in html
    assert 'scope="col"' in html


@pytest.mark.parametrize(
    "block",
    [heading("H", 2), paragraph("P"), bullets(["i"]), quote("Q"), Block(type=BlockType.RULE)],
)
def test_every_block_kind_renders_to_html(block: Block) -> None:
    html = render_html(DocumentModel(title="T", blocks=[block]), inline_css=False)
    assert "<main>" in html


def test_the_print_stylesheet_is_inlined_when_asked() -> None:
    html = render_html(DocumentModel(title="T", blocks=[]), inline_css=True)
    assert "@page" in html


# ---------------------------------------------------------------- word


def word_of(model: DocumentModel) -> WordDocument:
    return WordDocument(io.BytesIO(docx_renderer.render(model)))


def test_word_uses_built_in_heading_styles() -> None:
    word = word_of(DocumentModel(title="T", blocks=[heading("Title", 1), heading("Sub", 2)]))
    styles = [p.style.name for p in word.paragraphs]
    assert "Heading 1" in styles
    assert "Heading 2" in styles


def test_word_uses_list_styles() -> None:
    word = word_of(DocumentModel(title="T", blocks=[bullets(["a", "b"], ordered=True)]))
    assert any(p.style.name == "List Number" for p in word.paragraphs)


def test_word_carries_the_document_language() -> None:
    word = word_of(DocumentModel(title="T", language="mr", blocks=[paragraph("x")]))
    assert word.core_properties.language == "mr"


def test_word_renders_a_rule_visibly() -> None:
    word = word_of(DocumentModel(title="T", blocks=[Block(type=BlockType.RULE)]))
    assert any("*" in p.text for p in word.paragraphs)


def test_word_handles_an_empty_table() -> None:
    model = DocumentModel(title="T", blocks=[Block(type=BlockType.TABLE, rows=[])])
    assert docx_renderer.render(model)


def test_word_preserves_bold_and_italic() -> None:
    model = parse("Plain **bold** and *italic*.")
    word = word_of(model)
    runs = [run for p in word.paragraphs for run in p.runs]
    assert any(run.bold for run in runs)
    assert any(run.italic for run in runs)


# ---------------------------------------------------------------- pdf


def test_pdf_renders_a4_with_metadata() -> None:
    model = DocumentModel(
        title="Deposit request",
        language="en",
        blocks=[heading("Letter", 1), paragraph("Body 60,000.")],
    )
    data = pdf_renderer.render(model)
    assert data.startswith(b"%PDF-")

    with pdfplumber.open(io.BytesIO(data)) as pdf:
        assert 592 < pdf.pages[0].width < 598
        assert 839 < pdf.pages[0].height < 845
        assert pdf.metadata.get("Title") == "Deposit request"
        assert "60,000" in (pdf.pages[0].extract_text() or "")


def test_pdf_renders_devanagari() -> None:
    model = DocumentModel(
        title="पत्र", language="mr", blocks=[paragraph("रुपये साठ हजार परत मिळावेत.")]
    )
    assert pdf_renderer.render(model).startswith(b"%PDF-")


@pytest.mark.parametrize(
    "url",
    [
        "https://evil.example/steal.css",
        "http://169.254.169.254/latest/meta-data/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "data:text/css;base64,Ym9keXt9",
        "//protocol-relative.example/x.css",
    ],
)
def test_the_pdf_renderer_refuses_every_fetch(url: str) -> None:
    """A rendered document can contain user text. It must fetch nothing at all."""
    with pytest.raises(ExportError):
        pdf_renderer.no_network_fetcher(url)


def test_a_document_referencing_an_external_image_still_renders() -> None:
    """The refusal must degrade, not crash the export."""
    model = DocumentModel(title="T", blocks=[paragraph("Body text with no assets.")])
    assert pdf_renderer.render(model).startswith(b"%PDF-")
