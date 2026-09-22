"""Render a document model as HTML.

Used for the print view and as WeasyPrint's input. Every piece of text goes
through :func:`html.escape`, so a fact containing markup prints literally.
"""

from html import escape
from typing import Final

from app.config import TEMPLATES_DIR
from app.domain.document_model import Block, BlockType, DocumentModel, Run

PRINT_CSS_PATH: Final = TEMPLATES_DIR / "print.css"


def render(document: DocumentModel, *, inline_css: bool = True) -> str:
    """Render a complete HTML document.

    Args:
        document: The document model.
        inline_css: Whether to inline the print stylesheet. WeasyPrint is given
            no network access, so the CSS must travel with the document.

    Returns:
        A complete HTML document.
    """
    body = "\n".join(render_block(block) for block in document.blocks)
    style = f"<style>{PRINT_CSS_PATH.read_text(encoding='utf-8')}</style>" if inline_css else ""
    return (
        f'<!doctype html><html lang="{escape(document.language)}"><head>'
        f'<meta charset="utf-8"><title>{escape(document.title)}</title>{style}'
        f"</head><body><main>{body}</main></body></html>"
    )


def render_block(block: Block) -> str:
    """Render one block.

    Args:
        block: The block.

    Returns:
        Its HTML.
    """
    if block.type is BlockType.HEADING:
        return f"<h{block.level}>{_runs(block.runs)}</h{block.level}>"
    if block.type is BlockType.LIST:
        tag = "ol" if block.ordered else "ul"
        items = "".join(f"<li>{escape(item)}</li>" for item in block.items)
        return f"<{tag}>{items}</{tag}>"
    if block.type is BlockType.QUOTE:
        return f"<blockquote><p>{_runs(block.runs)}</p></blockquote>"
    if block.type is BlockType.TABLE:
        return _table(block)
    if block.type is BlockType.RULE:
        return "<hr>"
    return f"<p>{_runs(block.runs)}</p>"


def _table(block: Block) -> str:
    """Render a table with a real header row that repeats when printed."""
    head = ""
    body_rows = block.rows
    if block.rows and any(cell.header for cell in block.rows[0]):
        cells = "".join(f'<th scope="col">{_runs(cell.runs)}</th>' for cell in block.rows[0])
        head = f"<thead><tr>{cells}</tr></thead>"
        body_rows = block.rows[1:]

    body = "".join(
        "<tr>" + "".join(f"<td>{_runs(cell.runs)}</td>" for cell in row) + "</tr>"
        for row in body_rows
    )
    return f'<table class="ctable">{head}<tbody>{body}</tbody></table>'


def _runs(runs: list[Run]) -> str:
    """Render inline runs, escaping every character of text."""
    parts = []
    for run in runs:
        text = escape(run.text)
        if run.bold:
            text = f"<strong>{text}</strong>"
        if run.italic:
            text = f"<em>{text}</em>"
        parts.append(text)
    return "".join(parts)
