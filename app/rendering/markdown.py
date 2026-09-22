"""Parse a rendered Markdown template into a typed document model.

Only the constructs a letter needs are accepted. Anything else in the token
stream is ignored rather than passed through, so a fact that somehow contained
markup cannot introduce a construct the renderers were not designed for.
"""

from typing import Any

from markdown_it import MarkdownIt

from app.domain.document_model import Block, BlockType, Cell, DocumentModel, Run

#: A deliberately small parser: no HTML, no autolinks, no typographer.
_PARSER = MarkdownIt("zero").enable(
    ["heading", "list", "emphasis", "blockquote", "table", "hr", "escape"]
)


def parse(
    markdown: str, *, title: str = "", language: str = "en", facts: set[str] | None = None
) -> DocumentModel:
    """Parse Markdown into a document model.

    Args:
        markdown: The rendered template.
        title: Title metadata for the exported file.
        language: BCP 47 tag for the exported file.
        facts: Values the user confirmed, marked in the preview so they can see
            which parts of the letter are theirs.

    Returns:
        The document model.
    """
    tokens = _PARSER.parse(markdown)
    blocks: list[Block] = []
    index = 0
    while index < len(tokens):
        block, index = _read_block(tokens, index, facts or set())
        if block is not None:
            blocks.append(block)
    return DocumentModel(title=title, language=language, blocks=blocks)


def _read_block(tokens: list[Any], index: int, facts: set[str]) -> tuple[Block | None, int]:
    """Read one block starting at ``index``.

    Returns:
        The block, if the token opened one, and the index to continue from.
    """
    token = tokens[index]
    readers = {
        "heading_open": _read_heading,
        "paragraph_open": _read_paragraph,
        "bullet_list_open": _read_list,
        "ordered_list_open": _read_list,
        "blockquote_open": _read_quote,
        "table_open": _read_table,
    }
    if token.type == "hr":
        return (Block(type=BlockType.RULE), index + 1)
    reader = readers.get(token.type)
    if reader is None:
        return (None, index + 1)
    return reader(tokens, index, facts)


def _read_heading(tokens: list[Any], index: int, facts: set[str]) -> tuple[Block, int]:
    """Read a heading and its inline content."""
    level = int(tokens[index].tag[1])
    runs = _runs(tokens[index + 1], facts)
    return (Block(type=BlockType.HEADING, level=min(level, 4), runs=runs), index + 3)


def _read_paragraph(tokens: list[Any], index: int, facts: set[str]) -> tuple[Block, int]:
    """Read a paragraph and its inline content."""
    return (Block(type=BlockType.PARAGRAPH, runs=_runs(tokens[index + 1], facts)), index + 3)


def _read_quote(tokens: list[Any], index: int, facts: set[str]) -> tuple[Block, int]:
    """Read a block quote, flattening it to one quoted paragraph."""
    end = _matching(tokens, index, "blockquote_open", "blockquote_close")
    runs: list[Run] = []
    for position in range(index + 1, end):
        if tokens[position].type == "inline":
            runs.extend(_runs(tokens[position], facts))
    return (Block(type=BlockType.QUOTE, runs=runs), end + 1)


def _read_list(tokens: list[Any], index: int, facts: set[str]) -> tuple[Block, int]:
    """Read a list, flattening each item to plain text."""
    ordered = tokens[index].type == "ordered_list_open"
    close = "ordered_list_close" if ordered else "bullet_list_close"
    end = _matching(tokens, index, tokens[index].type, close)
    items = [
        "".join(run.text for run in _runs(tokens[position], facts))
        for position in range(index + 1, end)
        if tokens[position].type == "inline"
    ]
    return (Block(type=BlockType.LIST, ordered=ordered, items=items), end + 1)


def _read_table(tokens: list[Any], index: int, facts: set[str]) -> tuple[Block, int]:
    """Read a table into rows of cells."""
    end = _matching(tokens, index, "table_open", "table_close")
    rows: list[list[Cell]] = []
    current: list[Cell] = []
    header = False

    for position in range(index + 1, end):
        token = tokens[position]
        if token.type == "thead_open":
            header = True
        elif token.type == "thead_close":
            header = False
        elif token.type == "tr_open":
            current = []
        elif token.type == "tr_close":
            rows.append(current)
        elif token.type == "inline":
            current.append(Cell(runs=_runs(token, facts), header=header))

    return (Block(type=BlockType.TABLE, rows=rows), end + 1)


def _matching(tokens: list[Any], index: int, open_type: str, close_type: str) -> int:
    """Find the token that closes the one at ``index``."""
    depth = 0
    for position in range(index, len(tokens)):
        if tokens[position].type == open_type:
            depth += 1
        elif tokens[position].type == close_type:
            depth -= 1
            if depth == 0:
                return position
    return len(tokens) - 1


def _runs(inline: Any, facts: set[str]) -> list[Run]:
    """Convert an inline token's children into formatted runs."""
    runs: list[Run] = []
    bold = False
    italic = False

    for child in getattr(inline, "children", None) or []:
        if child.type == "strong_open":
            bold = True
        elif child.type == "strong_close":
            bold = False
        elif child.type == "em_open":
            italic = True
        elif child.type == "em_close":
            italic = False
        elif child.type in {"text", "code_inline"}:
            runs.extend(_split_on_facts(child.content, bold=bold, italic=italic, facts=facts))
        elif child.type in {"softbreak", "hardbreak"}:
            runs.append(Run(text=" ", bold=bold, italic=italic))

    return [run for run in runs if run.text]


def _split_on_facts(text: str, *, bold: bool, italic: bool, facts: set[str]) -> list[Run]:
    """Split text so the parts that came from a confirmed fact are marked.

    Marking them lets the preview underline the reader's own words, which is how
    they can see at a glance which parts of the letter are facts they confirmed.
    """
    candidates = sorted((fact for fact in facts if fact and fact in text), key=len, reverse=True)
    if not candidates:
        return [Run(text=text, bold=bold, italic=italic)]

    needle = candidates[0]
    head, _, tail = text.partition(needle)
    runs: list[Run] = []
    if head:
        runs.extend(_split_on_facts(head, bold=bold, italic=italic, facts=facts))
    runs.append(Run(text=needle, bold=bold, italic=italic, fact=True))
    if tail:
        runs.extend(_split_on_facts(tail, bold=bold, italic=italic, facts=facts))
    return runs
