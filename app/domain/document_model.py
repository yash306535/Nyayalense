"""One typed model for everything NyayaLens produces as a document.

The preview in the browser, the Word file and the PDF are all rendered from
this, so the three can never drift apart. It deliberately supports only a small
set of blocks: a letter needs headings, paragraphs, lists, tables and quotes,
and every extra feature is another way for user text to become markup.
"""

from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

Line = Annotated[str, Field(max_length=4000)]

MAX_HEADING_LEVEL = 4


class BlockType(StrEnum):
    """The kinds of block a rendered document may contain."""

    HEADING = "heading"
    PARAGRAPH = "paragraph"
    LIST = "list"
    TABLE = "table"
    QUOTE = "quote"
    RULE = "rule"


class Run(BaseModel):
    """A span of text with its formatting.

    Attributes:
        text: The characters. Always plain text: never markup.
        bold: Whether to render it bold.
        italic: Whether to render it italic.
        fact: True when the text came from a fact the user confirmed. The
            preview marks these so a reader can see which parts are theirs.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    text: Line
    bold: bool = False
    italic: bool = False
    fact: bool = False


class Cell(BaseModel):
    """One table cell."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    runs: list[Run] = Field(default_factory=list)
    header: bool = False

    @property
    def text(self) -> str:
        """The cell's plain text."""
        return "".join(run.text for run in self.runs)


class Block(BaseModel):
    """One block of a document.

    Only the fields relevant to :attr:`type` are populated; the rest stay at
    their defaults, which keeps the model flat and easy to render.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    type: BlockType
    runs: list[Run] = Field(default_factory=list)
    level: Annotated[int, Field(ge=1, le=MAX_HEADING_LEVEL)] = 1
    ordered: bool = False
    items: list[Line] = Field(default_factory=list)
    rows: list[list[Cell]] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """The block's plain text, for the fact audit and for tests."""
        if self.type is BlockType.LIST:
            return "\n".join(self.items)
        if self.type is BlockType.TABLE:
            return "\n".join(" ".join(cell.text for cell in row) for row in self.rows)
        return "".join(run.text for run in self.runs)


class DocumentModel(BaseModel):
    """A complete rendered document.

    Attributes:
        title: Used as the file's title metadata, which screen readers announce.
        language: BCP 47 tag, set on the file so text is read in the right voice.
        blocks: The content, in order.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    title: Annotated[str, Field(max_length=300)] = ""
    language: Annotated[str, Field(max_length=16)] = "en"
    blocks: list[Block] = Field(default_factory=list)

    @property
    def text(self) -> str:
        """The whole document as plain text."""
        return "\n\n".join(block.text for block in self.blocks)


def paragraph(text: str, *, fact: bool = False) -> Block:
    """Build a single-run paragraph.

    Args:
        text: The paragraph text.
        fact: Whether it came from a confirmed fact.

    Returns:
        The block.
    """
    return Block(type=BlockType.PARAGRAPH, runs=[Run(text=text, fact=fact)])


def heading(text: str, level: int = 2) -> Block:
    """Build a heading.

    Args:
        text: The heading text.
        level: Heading level, 1 to 4.

    Returns:
        The block.
    """
    return Block(type=BlockType.HEADING, level=min(level, MAX_HEADING_LEVEL), runs=[Run(text=text)])


def bullets(items: list[str], *, ordered: bool = False) -> Block:
    """Build a list.

    Args:
        items: The items.
        ordered: Whether to number them.

    Returns:
        The block.
    """
    return Block(type=BlockType.LIST, ordered=ordered, items=items)


def table(rows: list[list[str]], *, header: bool = True) -> Block:
    """Build a table.

    Args:
        rows: Rows of cell text, the first being the header row.
        header: Whether the first row is a header row.

    Returns:
        The block.
    """
    return Block(
        type=BlockType.TABLE,
        rows=[
            [Cell(runs=[Run(text=cell)], header=header and index == 0) for cell in row]
            for index, row in enumerate(rows)
        ],
    )


def quote(text: str) -> Block:
    """Build a block quote.

    Args:
        text: The quoted text.

    Returns:
        The block.
    """
    return Block(type=BlockType.QUOTE, runs=[Run(text=text, italic=True)])
