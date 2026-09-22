"""Turn extracted page text into a stable clause map.

Citations are only useful if they point somewhere a person can find, so the unit
of evidence is the clause the document numbered itself, not an arbitrary chunk.
Numbering styles vary wildly across Indian contract drafting, so several are
recognised, with a paragraph fallback when a document numbers nothing.
"""

import re
from dataclasses import dataclass, field
from typing import Final

from app.constants import CLAUSE_ID_PREFIX, MAX_CLAUSE_CHARS
from app.domain.models import Clause
from app.domain.normalize import DEVANAGARI_DIGITS, to_nfc

_DEV = DEVANAGARI_DIGITS

#: Numbering styles recognised at the start of a line, most specific first.
_NUMBER_PATTERNS: Final[tuple[str, ...]] = (
    rf"(?:clause|article|section|para(?:graph)?|\u0915\u0932\u092e|\u0927\u093e\u0930\u093e|"
    rf"\u0905\u0928\u0941\u091a\u094d\u091b\u0947\u0926)\s+"
    rf"([0-9{_DEV}]+(?:\.[0-9]+)*[A-Za-z]?|(?-i:[IVXL]{{1,6}}))\.?",
    r"([IVXL]+)\.",  # Article IV.
    rf"([0-9{_DEV}]+(?:\.[0-9{_DEV}]+)+)",  # 1.1, 1.1.2
    rf"([0-9{_DEV}]+)[.)]",  # 1.  1)
    r"\(([a-z])\)",  # (a)
    r"\(([ivxl]+)\)",  # (iv)
    r"([a-z])[.)]",  # a.  a)
)

_NUMBER_RE: Final = re.compile(
    r"^\s*(?:" + "|".join(f"(?:{pattern})" for pattern in _NUMBER_PATTERNS) + r")\s+(?=\S)",
    re.IGNORECASE,
)

#: Blocks that restart numbering and deserve their own heading.
_ANNEXURE_RE: Final = re.compile(
    r"^\s*(schedule|annexure|annex|appendix|exhibit|परिशिष्ट)\b[^\n]{0,80}$", re.IGNORECASE
)

#: A short line with no terminal punctuation reads as a heading.
_MAX_HEADING_CHARS: Final = 90

_SENTENCE_END_RE: Final = re.compile(r"(?<=[.;:\u0964?!])\s+")

#: Share of a line's letters that must be capitals for it to read as a heading.
_HEADING_UPPER_SHARE: Final = 0.6

_PAGE_NUMBER_RE: Final = re.compile(
    r"^\s*(?:page\s+)?[-\u2013\u2014]?\s*[0-9]+\s*(?:of\s+[0-9]+)?[-\u2013\u2014]?\s*$",
    re.IGNORECASE,
)

#: A line appearing on at least this share of pages is running furniture.
_REPEAT_THRESHOLD: Final = 0.5

#: Below this many pages, repetition is coincidence rather than a header.
_MIN_PAGES_FOR_REPEAT_CHECK: Final = 3

_HYPHEN_BREAK_RE: Final = re.compile(r"(\w)[-\u2010\u2011]\n(\w)")


@dataclass(slots=True)
class _Block:
    """A clause under construction."""

    label: str
    heading: str
    lines: list[str] = field(default_factory=list)
    page: int = 1

    def text(self) -> str:
        """Join the block's lines into one paragraph."""
        return " ".join(line.strip() for line in self.lines if line.strip()).strip()


def clean_pages(pages: list[str]) -> list[str]:
    """Remove running headers, footers and page numbers.

    Args:
        pages: Extracted text, one entry per page.

    Returns:
        The pages with repeated furniture and bare page numbers removed.
    """
    repeated = _repeated_lines(pages)
    cleaned: list[str] = []
    for page in pages:
        kept = [
            line
            for line in page.splitlines()
            if line.strip() and line.strip() not in repeated and not _PAGE_NUMBER_RE.match(line)
        ]
        cleaned.append("\n".join(kept))
    return cleaned


def _repeated_lines(pages: list[str]) -> set[str]:
    """Find lines that appear on at least half the pages."""
    if len(pages) < _MIN_PAGES_FOR_REPEAT_CHECK:
        return set()
    counts: dict[str, int] = {}
    for page in pages:
        for line in {line.strip() for line in page.splitlines() if line.strip()}:
            counts[line] = counts.get(line, 0) + 1
    threshold = len(pages) * _REPEAT_THRESHOLD
    return {line for line, count in counts.items() if count >= threshold}


def join_hyphenated_breaks(text: str) -> str:
    """Rejoin words a line break split with a hyphen."""
    return _HYPHEN_BREAK_RE.sub(r"\1\2", text)


def _match_number(line: str) -> tuple[str, str] | None:
    """Split a numbered line into its label and the rest.

    Args:
        line: One line of document text.

    Returns:
        ``(label, remainder)``, or ``None`` when the line is not numbered.
    """
    match = _NUMBER_RE.match(line)
    if match is None:
        return None
    label = next((group for group in match.groups() if group), "")
    return (label, line[match.end() :].strip())


def _looks_like_heading(line: str) -> bool:
    """Decide whether a short unnumbered line is a heading."""
    stripped = line.strip()
    if not stripped or len(stripped) > _MAX_HEADING_CHARS:
        return False
    if stripped[-1] in ".,;":
        return False
    letters = [character for character in stripped if character.isalpha()]
    if not letters:
        return False
    upper_share = sum(character.isupper() for character in letters) / len(letters)
    return upper_share > _HEADING_UPPER_SHARE or stripped.istitle()


def split_into_blocks(pages: list[str]) -> list[_Block]:
    """Group cleaned page text into numbered or headed blocks.

    Args:
        pages: Cleaned text, one entry per page.

    Returns:
        Blocks in document order. Text before the first heading becomes a
        preamble block.
    """
    blocks: list[_Block] = []
    current = _Block(label="", heading="", page=1)

    for page_number, page in enumerate(pages, start=1):
        for raw_line in page.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            numbered = _match_number(line)
            annexure = _ANNEXURE_RE.match(line)

            if numbered is not None:
                label, remainder = numbered
                blocks.append(current)
                current = _Block(label=label, heading="", page=page_number)
                if remainder:
                    if _looks_like_heading(remainder):
                        current.heading = remainder
                    else:
                        current.lines.append(remainder)
            elif _looks_like_heading(line) and not current.lines and not current.heading:
                current.heading = line  # a title before any body text
            elif annexure or (_looks_like_heading(line) and current.lines):
                blocks.append(current)
                current = _Block(label="", heading=line, page=page_number)
            else:
                current.lines.append(line)

    blocks.append(current)
    return [block for block in blocks if block.text() or block.heading]


def _split_long_text(text: str) -> list[str]:
    """Split an over-long block at sentence boundaries.

    Args:
        text: Block text longer than :data:`~app.constants.MAX_CLAUSE_CHARS`.

    Returns:
        Parts, each at most roughly the limit, split only between sentences.
    """
    sentences = _SENTENCE_END_RE.split(text)
    parts: list[str] = []
    buffer = ""
    for sentence in sentences:
        candidate = f"{buffer} {sentence}".strip() if buffer else sentence
        if buffer and len(candidate) > MAX_CLAUSE_CHARS:
            parts.append(buffer)
            buffer = sentence
        else:
            buffer = candidate
    if buffer:
        parts.append(buffer)
    return parts or [text]


def segment(pages: list[str]) -> list[Clause]:
    """Build the clause map for a document.

    Args:
        pages: Extracted text, one entry per page, before cleaning.

    Returns:
        Clauses with stable ids, the document's own labels, page numbers and
        offsets into the joined document text.
    """
    cleaned = [join_hyphenated_breaks(to_nfc(page)) for page in clean_pages(pages)]
    clauses: list[Clause] = []
    offset = 0
    number = 0

    for block in split_into_blocks(cleaned):
        body = block.text() or block.heading
        if not body:
            continue
        number += 1
        parts = _split_long_text(body) if len(body) > MAX_CLAUSE_CHARS else [body]
        for index, part in enumerate(parts):
            suffix = chr(ord("a") + index) if len(parts) > 1 else ""
            clauses.append(
                Clause(
                    id=f"{CLAUSE_ID_PREFIX}{number}{suffix}",
                    label=block.label,
                    heading=block.heading,
                    text=part,
                    page=block.page,
                    start=offset,
                    end=offset + len(part),
                )
            )
            offset += len(part) + 2  # the blank line that joins clauses in full text

    return clauses
