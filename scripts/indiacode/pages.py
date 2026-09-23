"""Turn the pages of an India Code act PDF into lines of text.

This module decides what is actually printed on a page, and nothing about what
the act says. What it drops is page furniture, and only page furniture:

* Every page carries a diagonal grey "India Code" watermark. Its glyphs land in
  the middle of sentences when a page is read naively, turning ``WHO`` into
  ``WIHO``. It is set large and grey, so it is dropped on both counts.
* Footnotes sit below a short rule at the left margin, and the page number sits
  below them. Everything from that rule down goes.
* Amendment references are superscript digits. Left in, they read as part of a
  word (``threat or 2promise``), so they go too. The square brackets they
  introduce stay, because they are part of what the page shows.
* Chapter and cross-headings are centred, and body text is not, so centred lines
  go -- except the few labels a section's own text is built from.

Each line keeps a note of which of its characters were set in bold, because that
is what marks the end of a section's title further up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

import pdfplumber

#: Point size at or above which text is the watermark, not the page.
WATERMARK_MIN_SIZE: Final = 20.0

#: Point size at or below which a digit is a superscript amendment marker.
FOOTNOTE_MARKER_MAX_SIZE: Final = 7.5

#: The rule drawn above a page's footnotes: short, hairline, below the middle.
RULE_MAX_HEIGHT: Final = 2.0
RULE_MIN_WIDTH: Final = 100.0
RULE_MAX_WIDTH: Final = 200.0

#: Bottom strip holding the page number, used when a page has no footnote rule.
PAGE_NUMBER_MARGIN: Final = 60.0

#: A line indented this far from the left, and ending this far from the right,
#: is centred, which in these PDFs means a heading rather than body text.
CENTRED_MIN_LEFT: Final = 150.0
CENTRED_MIN_RIGHT: Final = 100.0

#: Centred lines that are part of an act rather than a heading above one: the
#: labels inside a section, and the banner that opens the state variants.
KEEP_CENTRED: Final = re.compile(
    r"^(?:Illustrations?|Exception|Explanation|STATE\s+AMENDMENTS?)\b", re.IGNORECASE
)

BOLD: Final = "B"
ROMAN: Final = "."


@dataclass(frozen=True, slots=True)
class Line:
    """One printed line, with a bold/not-bold flag for each character.

    Attributes:
        text: The line as printed.
        weight: One character per character of ``text``: ``B`` where the glyph
            is bold, ``.`` where it is not.
        page: The 1-based page the line appears on.
    """

    text: str
    weight: str
    page: int


def _footnote_rule_top(page: Any) -> float | None:
    """Find where a page's footnotes begin, if it has any."""
    for rect in page.rects:
        width = rect["x1"] - rect["x0"]
        if (
            rect["height"] <= RULE_MAX_HEIGHT
            and RULE_MIN_WIDTH < width < RULE_MAX_WIDTH
            and rect["top"] > page.height / 2
        ):
            return float(rect["top"])
    return None


def _is_body_char(obj: dict[str, Any], limit: float) -> bool:
    """Say whether one glyph is part of the page's text."""
    if obj.get("object_type") != "char":
        return True
    size = float(obj.get("size", 0.0))
    if size >= WATERMARK_MIN_SIZE or size <= FOOTNOTE_MARKER_MAX_SIZE:
        return False
    if tuple(obj.get("non_stroking_color") or ()) not in ((0.0,), ()):
        return False
    return float(obj["top"]) < limit


def _weights(line: dict[str, Any]) -> str:
    """Mark each character of a line bold or not.

    pdfplumber inserts spaces that have no glyph behind them, so the glyphs are
    walked alongside the text rather than zipped with it.

    Args:
        line: One line from ``extract_text_lines``.

    Returns:
        A string as long as ``line["text"]``.
    """
    glyphs = [char for char in line["chars"] if not char["text"].isspace()]
    out: list[str] = []
    index = 0
    for character in line["text"]:
        if character.isspace():
            out.append(out[-1] if out else ROMAN)
            continue
        bold = index < len(glyphs) and "Bold" in glyphs[index]["fontname"]
        out.append(BOLD if bold else ROMAN)
        index += 1
    return "".join(out)


def trim(text: str, weight: str) -> tuple[str, str]:
    """Strip a line's outer whitespace, keeping its weights in step with it."""
    start = len(text) - len(text.lstrip())
    stripped = text.strip()
    return stripped, weight[start : start + len(stripped)]


def _page_lines(page: Any, number: int) -> list[Line]:
    """Read one page, dropping the watermark, footnotes and headings."""
    limit = min(_footnote_rule_top(page) or page.height, page.height - PAGE_NUMBER_MARGIN)
    kept = page.filter(lambda obj: _is_body_char(obj, limit))
    lines = []
    for line in kept.extract_text_lines():
        text, weight = trim(line["text"], _weights(line))
        if not text:
            continue
        centred = line["x0"] > CENTRED_MIN_LEFT and line["x1"] < page.width - CENTRED_MIN_RIGHT
        if centred and not KEEP_CENTRED.match(text):
            continue
        lines.append(Line(text=text, weight=weight, page=number))
    return lines


def read_lines(path: Path) -> list[Line]:
    """Read every body line of an act PDF, in printed order.

    Args:
        path: The PDF in ``data_sources/``.

    Returns:
        Its lines, in the order they are printed.
    """
    lines: list[Line] = []
    with pdfplumber.open(path) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            lines.extend(_page_lines(page, number))
    return lines
