#!/usr/bin/env python3
"""Build the law mapping files from the official correspondence tables.

The tables are published as PDFs by the Bureau of Police Research & Development.
Place them in ``data_sources/`` (see its README) and run ``make laws-data``.

What this script will not do is invent a row. Every row it writes carries the
document and page it came from, and is marked ``extracted`` until a person has
checked it against that page and marked it ``verified``. Rows still marked
``extracted`` are hidden from users unless ``LAW_DATA_SHOW_UNREVIEWED`` is on,
and carry a visible label when they are shown.

The three published tables are laid out slightly differently from each other
(the IEA-to-BSA table puts the old section first; the other two put the new
section first), and a handful of rows in each cite something other than a
plain section number (a proviso, an explanation, a schedule item). Those rows
are skipped and counted rather than guessed at.

Usage:
    python scripts/build_law_data.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Final, Literal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.enums import ChangeType, LawAct  # noqa: E402
from app.domain.laws.models import LawMapping, LawTransition, ProvisionRef, Source  # noqa: E402

SOURCE_DIR: Final = PROJECT_ROOT / "data_sources"
OUTPUT_DIR: Final = PROJECT_ROOT / "app" / "data" / "laws" / "mappings"

SOURCE_NOTE: Final = (
    "Correspondence tables published by the Bureau of Police Research & Development "
    "(https://bprd.nic.in), under 'Nyaya Sanhita' > 'Documents by BPR&D'. They are a "
    "police training aid and reference document, not a statutory instrument."
)

IN_FORCE_FROM: Final = "2024-07-01"

#: A note explaining why a "no equivalent" row could not come from extraction.
_NOT_CARRIED_FORWARD_NOTE: Final = (
    "Publicly reported as not carried forward into the new code. This BNS-to-IPC "
    "table is organised by the new code, so a section with no new counterpart has "
    "no row to extract; this entry was added by hand and still needs confirming "
    "against the official gazette text before it can be marked verified."
)

#: Old provisions known to have no new-code counterpart, keyed by transition id.
#: The BPR&D table cannot surface these (see the note above), so they are the
#: one thing this script adds by hand rather than extracts. Each still ships
#: marked 'extracted', not 'verified': a person must confirm it before it is
#: shown to a user.
KNOWN_NOT_CARRIED_FORWARD: Final[dict[str, tuple[tuple[str, str], ...]]] = {
    "ipc_bns": (
        ("124A", "Sedition."),
        ("377", "Unnatural offences."),
        ("497", "Adultery."),
    ),
}

#: Longest note/title text a row keeps. Anything longer is truncated: the
#: schema caps these fields, and a truncated note is honest where a silently
#: dropped row would not be.
MAX_TEXT_CHARS: Final = 480

ColumnOrder = Literal["new_first", "old_first"]


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    """One old act replaced by one new act, and the PDF that maps them.

    Attributes:
        column_order: Which side of the comparison the table lists first.
            The BPR&D tables are not laid out consistently with each other.
    """

    id: str
    old_act: LawAct
    new_act: LawAct
    old_name: str
    new_name: str
    filename: str
    column_order: ColumnOrder = "new_first"


SPECS: Final[tuple[TransitionSpec, ...]] = (
    TransitionSpec(
        "ipc_bns",
        LawAct.IPC,
        LawAct.BNS,
        "Indian Penal Code, 1860",
        "Bharatiya Nyaya Sanhita, 2023",
        "bprd-ipc-bns.pdf",
        column_order="new_first",
    ),
    TransitionSpec(
        "crpc_bnss",
        LawAct.CRPC,
        LawAct.BNSS,
        "Code of Criminal Procedure, 1973",
        "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "bprd-crpc-bnss.pdf",
        column_order="new_first",
    ),
    TransitionSpec(
        "iea_bsa",
        LawAct.IEA,
        LawAct.BSA,
        "Indian Evidence Act, 1872",
        "Bharatiya Sakshya Adhiniyam, 2023",
        "bprd-iea-bsa.pdf",
        column_order="old_first",
    ),
)

#: A plain section number, the only form our schema can represent: digits with
#: an optional one- or two-letter suffix (like 498A, 65B). The tables also cite
#: provisos, explanations and illustrations by name; those do not match and are
#: skipped rather than forced into a section number they are not.
SECTION_RE: Final = re.compile(r"^(\d{1,3}[A-Za-z]{0,2})\b")

#: Cell values meaning "this side has no counterpart", however the table spells it.
NO_EQUIVALENT_MARKERS: Final = frozenset({"-", "--", "—", "new", "nil", "none", "n/a", ""})

#: Wording the tables use for a row with no substantive change.
NO_CHANGE_MARKERS: Final = ("no change", "same as")

EXPECTED_COLUMNS: Final = 4


@dataclass(frozen=True, slots=True)
class RawRow:
    """One row exactly as the table printed it, before grouping."""

    old_section: str
    new_section: str
    title: str
    note: str
    page: int


@dataclass
class Row:
    """Rows grouped by old section, ready to become one mapping."""

    old_section: str
    title: str
    new_sections: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    page: int = 0


def extract_rows(pdf_path: Path, *, column_order: ColumnOrder) -> tuple[list[RawRow], int]:
    """Pull the table rows out of one correspondence PDF.

    Args:
        pdf_path: The official PDF.
        column_order: Which side of the comparison the table lists first.

    Returns:
        The rows that parsed cleanly, and a count of rows skipped because
        either section cell was not a plain section number.
    """
    import pdfplumber  # noqa: PLC0415 - only needed when the script actually runs

    rows: list[RawRow] = []
    skipped = 0
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                parsed, page_skipped = _rows_from_table(table, page_number, column_order)
                rows.extend(parsed)
                skipped += page_skipped
    return rows, skipped


def _rows_from_table(
    table: list[list[str | None]], page: int, column_order: ColumnOrder
) -> tuple[list[RawRow], int]:
    """Convert one extracted table into raw rows, skipping what does not parse.

    The two layouts put the title in a different column, not just the old and
    new sections in a different order:

    - ``new_first``: new section, title, old section, note
    - ``old_first``:  old section, new section, title, note
    """
    parsed: list[RawRow] = []
    skipped = 0
    for raw in table:
        cells = [_clean(cell) for cell in raw]
        if len(cells) < EXPECTED_COLUMNS:
            continue

        if column_order == "old_first":
            old_cell, new_cell, title, note = cells[0], cells[1], cells[2], cells[3]
        else:
            new_cell, title, old_cell, note = cells[0], cells[1], cells[2], cells[3]

        old_section = _section_number(old_cell)
        new_section = _section_number(new_cell)
        if old_section is None or new_section is None:
            skipped += 1
            continue

        parsed.append(
            RawRow(
                old_section=old_section,
                new_section=new_section,
                title=title[:MAX_TEXT_CHARS],
                note=note[:MAX_TEXT_CHARS],
                page=page,
            )
        )
    return parsed, skipped


def _clean(cell: str | None) -> str:
    """Collapse a cell's whitespace, including the newlines pdfplumber leaves in."""
    return re.sub(r"\s+", " ", (cell or "")).strip()


def _section_number(cell: str) -> str | None:
    """Read a plain section number out of a cell, or say it is not one.

    Args:
        cell: A cleaned cell value, such as ``"108A"`` or ``"103 (1)"``.

    Returns:
        The base section number, ignoring any subsection suffix (our schema is
        section-level, not subsection-level). ``None`` for a cell naming no
        old or new counterpart at all, and also for a cell that names
        something other than a section number, such as a proviso.
    """
    if cell.casefold() in NO_EQUIVALENT_MARKERS:
        return None
    match = SECTION_RE.match(cell)
    return match.group(1) if match else None


def _group_by_old_section(raw_rows: list[RawRow]) -> list[Row]:
    """Group raw rows by old section, since that is what a mapping is keyed on.

    Several raw rows can share one old section (a section split across
    subsections that each map differently), and this keeps every new section
    any of them names.

    Args:
        raw_rows: Every row that parsed.

    Returns:
        One :class:`Row` per distinct old section, in first-seen order.
    """
    grouped: dict[str, Row] = {}
    for raw in raw_rows:
        row = grouped.setdefault(
            raw.old_section, Row(old_section=raw.old_section, title=raw.title, page=raw.page)
        )
        if raw.new_section not in row.new_sections:
            row.new_sections.append(raw.new_section)
        if raw.note and raw.note not in row.notes:
            row.notes.append(raw.note)
    return list(grouped.values())


def _combined_note(row: Row) -> str:
    """Join a row's distinct notes, dropping plain "no change" markers."""
    substantive = [
        note
        for note in row.notes
        if not any(marker in note.casefold() for marker in NO_CHANGE_MARKERS)
    ]
    return " / ".join(substantive)[:MAX_TEXT_CHARS]


def classify(row: Row, note: str) -> ChangeType:
    """Decide how an old provision relates to the new code.

    Args:
        row: The grouped row.
        note: The row's combined, "no change" text already stripped out.

    Returns:
        The change type the row's own shape implies. This is arithmetic on the
        extracted cells, never a judgement about the law.
    """
    if len(row.new_sections) > 1:
        return ChangeType.SPLIT
    if note and "merg" in note.casefold():
        return ChangeType.MERGED
    if note:
        return ChangeType.MODIFIED
    return ChangeType.RENUMBERED


def build_transition(spec: TransitionSpec, raw_rows: list[RawRow]) -> LawTransition:
    """Turn extracted rows into a validated transition.

    Args:
        spec: Which acts these rows map between.
        raw_rows: Every row that parsed as a plain section reference.

    Returns:
        The transition, every row marked ``extracted``.
    """
    mappings = []
    for row in _group_by_old_section(raw_rows):
        note = _combined_note(row)
        mappings.append(
            LawMapping(
                old=ProvisionRef(act=spec.old_act, section=row.old_section, title=row.title),
                new=[
                    ProvisionRef(act=spec.new_act, section=section, title=row.title)
                    for section in sorted(row.new_sections)
                ],
                change_type=classify(row, note),
                note=note,
                source=Source(
                    document=f"BPR&D correspondence table: {spec.filename}", page=row.page
                ),
            )
        )
    mappings.extend(_known_gaps(spec))
    return LawTransition(
        id=spec.id,
        old_act=spec.old_act,
        new_act=spec.new_act,
        old_act_name=spec.old_name,
        new_act_name=spec.new_name,
        in_force_from=IN_FORCE_FROM,
        source_note=SOURCE_NOTE,
        mappings=mappings,
    )


def _known_gaps(spec: TransitionSpec) -> list[LawMapping]:
    """Build the hand-added rows for provisions this table cannot surface.

    Args:
        spec: Which transition to add gaps for.

    Returns:
        One row per known gap, empty when the transition has none recorded.
    """
    return [
        LawMapping(
            old=ProvisionRef(act=spec.old_act, section=section, title=title),
            new=[],
            change_type=ChangeType.NO_DIRECT_EQUIVALENT,
            note=_NOT_CARRIED_FORWARD_NOTE,
            source=Source(document="Publicly reported; not from the BPR&D table itself"),
        )
        for section, title in KNOWN_NOT_CARRIED_FORWARD.get(spec.id, ())
    ]


def write(transition: LawTransition, *, dry_run: bool) -> Path:
    """Write one transition file.

    Args:
        transition: The validated transition.
        dry_run: When true, report what would be written and change nothing.

    Returns:
        The path that was written, or would have been.
    """
    path = OUTPUT_DIR / f"{transition.id}.json"
    if dry_run:
        return path
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = transition.model_dump(mode="json", exclude_none=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    """Build every transition file from whatever PDFs are present."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing.")
    arguments = parser.parse_args()

    missing = [spec for spec in SPECS if not (SOURCE_DIR / spec.filename).exists()]
    if missing:
        print("Missing source PDFs in data_sources/:")
        for spec in missing:
            print(f"  - {spec.filename}  ({spec.old_name} -> {spec.new_name})")
        print("\nSee data_sources/README.md for where to download them.")
        if len(missing) == len(SPECS):
            return 1

    for spec in SPECS:
        source = SOURCE_DIR / spec.filename
        if not source.exists():
            continue
        raw_rows, skipped = extract_rows(source, column_order=spec.column_order)
        transition = build_transition(spec, raw_rows)
        path = write(transition, dry_run=arguments.dry_run)
        action = "would write" if arguments.dry_run else "wrote"
        print(
            f"{action} {path.name}: {len(transition.mappings)} old sections "
            f"from {len(raw_rows)} table rows ({skipped} skipped: not a plain section "
            f"number, such as a proviso or 'no counterpart' cell), all marked "
            f"'extracted' pending review"
        )

    print("\nNext: check each row against its source page, then set review_status")
    print("to 'verified' and add verified_on. See docs/DATA.md.")
    print(
        "\nNote: this table is organised by the new code, so a genuinely new "
        "provision with no old counterpart cannot appear as a row (the schema "
        "requires an old section). Sections known to have no new counterpart "
        "(IPC 124A, 377, 497) are not in this extraction either, for the "
        "opposite reason: they have no row in a new-code-first table. Add them "
        "by hand if you need them, as the previous seed data did."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
