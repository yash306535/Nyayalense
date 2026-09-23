"""Read the sections out of an India Code consolidated act PDF.

Where :mod:`scripts.indiacode.pages` decides what is printed, this module
decides what the act says. It relies on the way these PDFs are typeset rather
than on guesswork, and on one rule above all:

**A section's heading is set in bold and its text is not.** That is what marks
the end of a title, not the dash that usually follows it: a few sections have no
dash at all, and others carry a full stop inside the title.

Two things that look like sections are not. The arrangement of sections at the
front lists every number without its text, so reading starts after the enacting
formula that closes it. State legislatures' variants are printed beneath the
section they vary, sometimes under a number the act itself does not have; the
arrangement of sections is what tells the two apart.

Anything this reader cannot place is left out and counted, never guessed at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final

from scripts.indiacode.models import ExtractedSection
from scripts.indiacode.pages import BOLD, ROMAN, Line, read_lines

#: A section opening. The space after the number is missing here and there, so
#: what follows the full stop is looked at rather than required.
SECTION_START: Final = re.compile(r"^\[?(\d{1,3}[A-Za-z]{0,2})\.(?=\s|[A-Z“])")

#: Labels that begin a new line inside a section rather than continuing one.
PARAGRAPH_START: Final = re.compile(
    r"^(?:\([0-9A-Za-z]{1,4}\)|\[|(?:Explanation|Illustration|Exception|Provided)\b)"
)

#: Where state legislatures' variants begin. They are printed under the central
#: section they vary, and are not the text the correspondence tables compare, so
#: a section's text stops here.
STATE_AMENDMENT: Final = re.compile(r"^STATE\s+AMENDMENTS?\b", re.IGNORECASE)

#: The last line of the front matter.
ENACTING_FORMULA: Final = re.compile(r"enacted as follows", re.IGNORECASE)

#: A section wholly replaced by a later Act is printed inside square brackets,
#: so its line can open with a bracket that is not part of the heading.
AMENDMENT_BRACKET: Final = "["

#: The dashes India Code uses to introduce a section's text after its title.
DASHES: Final = "—–‒-"

#: Punctuation that closes a title but is sometimes set in roman, not bold.
TITLE_TAIL: Final = DASHES + ".”’'\" "

#: How much of an opening to quote back when it could not be read.
REPORT_CHARS: Final = 60


@dataclass(frozen=True, slots=True)
class PdfReadout:
    """Everything one act PDF yielded.

    Attributes:
        sections: The sections that parsed, in the order they are printed.
        repeated: Section numbers printed more than once; only the first is
            kept.
        untitled: Openings that carry a number but no title, which is how a
            repealed section is printed. They have no text to quote.
    """

    sections: list[ExtractedSection]
    repeated: list[str]
    untitled: list[str]


def _heading_offset(line: Line) -> int | None:
    """Find where a section's bold heading starts on this line.

    Args:
        line: One reflowed block.

    Returns:
        The index the heading starts at, or ``None`` when this is not a heading.
    """
    if not SECTION_START.match(line.text):
        return None
    offset = 1 if line.text.startswith(AMENDMENT_BRACKET) else 0
    return offset if line.weight[offset:].startswith(BOLD) else None


def reflow(lines: list[Line]) -> list[Line]:
    """Join lines the typesetter wrapped, keeping real paragraph breaks.

    A line continues the one above it unless it opens a section, a labelled
    paragraph, or a run of state variants. Titles that wrap over two lines are
    rejoined here, so the bold run that marks a title stays in one piece.

    Args:
        lines: Lines in printed order.

    Returns:
        One entry per paragraph.
    """
    blocks: list[Line] = []
    for line in lines:
        breaks = (
            _heading_offset(line) is not None
            or PARAGRAPH_START.match(line.text)
            or STATE_AMENDMENT.match(line.text)
        )
        if not blocks or breaks:
            blocks.append(line)
            continue
        previous = blocks[-1]
        joint = previous.weight[-1] if previous.weight else ROMAN
        blocks[-1] = Line(
            text=f"{previous.text} {line.text}",
            weight=previous.weight + joint + line.weight,
            page=previous.page,
        )
    return blocks


def _split_heading(block: Line, offset: int) -> tuple[str, str, str]:
    """Split a section block into its number, title and text.

    The bold run can stop a character or two short of the end of a title, where
    the full stop and dash that close it were set in roman, so punctuation
    immediately after the run is taken as part of the heading too.

    Args:
        block: A block that opens a section.
        offset: Where the heading starts, from ``_heading_offset``.

    Returns:
        The section number, the title as printed, and the text that follows.
        The title is empty when the heading carries none, which is how a
        repealed section is printed.
    """
    tail = block.weight[offset:]
    end = offset + len(tail) - len(tail.lstrip(BOLD))
    while end < len(block.text) and block.text[end] in TITLE_TAIL:
        end += 1
    heading, body = block.text[offset:end], block.text[end:]
    match = SECTION_START.match(heading)
    if match is None:
        return "", "", ""
    title = heading[match.end() :].strip().rstrip(DASHES + " ").strip()
    if title.startswith(AMENDMENT_BRACKET):
        # A repealed or omitted section prints its old title in brackets, with
        # the repealing Act in place of any text. There is nothing to quote.
        return match.group(1), "", ""
    return match.group(1), title, body.strip()


def _after_front_matter(blocks: list[Line]) -> list[Line]:
    """Drop the arrangement of sections, which lists numbers without text."""
    for index, block in enumerate(blocks):
        if ENACTING_FORMULA.search(block.text):
            return blocks[index + 1 :]
    return blocks


def listed_numbers(lines: list[Line]) -> frozenset[str]:
    """Read the section numbers out of the arrangement of sections.

    A state legislature's insertion is printed in the body of the act but is
    never listed at the front of it, so this is what tells the act's own
    sections apart from the variants printed beneath them.

    Args:
        lines: Lines in printed order.

    Returns:
        Every number the front matter lists.
    """
    numbers: set[str] = set()
    for line in lines:
        match = SECTION_START.match(line.text)
        if match:
            numbers.add(match.group(1))
        if ENACTING_FORMULA.search(line.text):
            break
    return frozenset(numbers)


@dataclass(slots=True)
class _Collector:
    """Sections as they accumulate, in printed order.

    Attributes:
        texts: The paragraphs read so far, keyed by section number.
        headings: Each section's title and the page it starts on.
        repeated: Numbers printed more than once.
        untitled: Openings with a number but no title.
        current: The section paragraphs are being added to.
        skipping: Whether the opening just read was one to leave out.
    """

    texts: dict[str, list[str]] = field(default_factory=dict)
    headings: dict[str, tuple[str, int]] = field(default_factory=dict)
    repeated: list[str] = field(default_factory=list)
    untitled: list[str] = field(default_factory=list)
    current: str = ""
    skipping: bool = False

    def open_section(self, block: Line, offset: int) -> None:
        """Start a section, or record why this opening was not one."""
        number, title, text = _split_heading(block, offset)
        self.skipping = True
        if not number or not title:
            self.untitled.append(block.text[:REPORT_CHARS])
        elif number in self.texts:
            self.repeated.append(number)
        else:
            self.texts[number] = [text] if text.strip() else []
            self.headings[number] = (title, block.page)
            self.current, self.skipping = number, False

    def add(self, text: str) -> None:
        """Add a paragraph to the section being read, if there is one."""
        if self.current and not self.skipping:
            self.texts[self.current].append(text)

    def readout(self, url: str) -> PdfReadout:
        """Close off what was collected."""
        return PdfReadout(
            sections=[
                ExtractedSection(
                    section=number,
                    title=self.headings[number][0],
                    text="\n".join(part for part in parts if part.strip()).strip(),
                    page=self.headings[number][1],
                    url=url,
                )
                for number, parts in self.texts.items()
            ],
            repeated=self.repeated,
            untitled=self.untitled,
        )


def _resumes(block: Line, offset: int, listed: frozenset[str], seen: dict[str, list[str]]) -> bool:
    """Say whether a heading ends a run of state variants.

    Args:
        block: A block that opens a section.
        offset: Where its heading starts.
        listed: The numbers the front matter lists.
        seen: The sections read so far.

    Returns:
        True when this heading is one of the act's own sections and has not been
        read yet, which is where the variants printed above it end.
    """
    match = SECTION_START.match(block.text[offset:])
    if match is None:
        return False
    number = match.group(1)
    return number in listed and number not in seen


def parse(lines: list[Line], *, url: str = "") -> PdfReadout:
    """Turn the lines of an act PDF into sections.

    Args:
        lines: Lines in printed order, as ``read_lines`` returns them.
        url: The public page these sections can be checked against.

    Returns:
        The sections, and what was left out.
    """
    listed = listed_numbers(lines)
    collector = _Collector()
    in_variant = False
    for block in _after_front_matter(reflow(lines)):
        offset = _heading_offset(block)
        if in_variant:
            if offset is None or not _resumes(block, offset, listed, collector.texts):
                continue
            in_variant = False
        elif STATE_AMENDMENT.match(block.text):
            in_variant = True
            continue
        if offset is None:
            collector.add(block.text)
        else:
            collector.open_section(block, offset)
    return collector.readout(url)


def extract(path: Path, *, url: str = "") -> PdfReadout:
    """Read one act PDF end to end.

    Args:
        path: The PDF in ``data_sources/``.
        url: The public page these sections can be checked against.

    Returns:
        Everything the PDF yielded.
    """
    return parse(read_lines(path), url=url)
