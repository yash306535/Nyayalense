#!/usr/bin/env python3
"""Build the law mapping files from the official correspondence tables.

The tables are published as PDFs by the Bureau of Police Research & Development.
Place them in ``data_sources/`` (see its README) and run ``make laws-data``.

What this script will not do is invent a row. Every row it writes carries the
document and page it came from, and is marked ``extracted`` until a person has
checked it against that page and marked it ``verified``. Rows still marked
``extracted`` are hidden from users unless ``LAW_DATA_SHOW_UNREVIEWED`` is on,
and carry a visible label when they are shown.

Usage:
    python scripts/build_law_data.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Final

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.enums import ChangeType, LawAct  # noqa: E402
from app.domain.laws.models import LawMapping, LawTransition, ProvisionRef, Source  # noqa: E402

SOURCE_DIR: Final = PROJECT_ROOT / "data_sources"
OUTPUT_DIR: Final = PROJECT_ROOT / "app" / "data" / "laws" / "mappings"

SOURCE_NOTE: Final = (
    "Correspondence tables published by the Bureau of Police Research & Development "
    "(https://bprd.nic.in), 21 June 2024. They are a police training aid and reference "
    "document, not a statutory instrument."
)

IN_FORCE_FROM: Final = "2024-07-01"


@dataclass(frozen=True, slots=True)
class TransitionSpec:
    """One old act replaced by one new act, and the PDF that maps them."""

    id: str
    old_act: LawAct
    new_act: LawAct
    old_name: str
    new_name: str
    filename: str


SPECS: Final[tuple[TransitionSpec, ...]] = (
    TransitionSpec(
        "ipc_bns",
        LawAct.IPC,
        LawAct.BNS,
        "Indian Penal Code, 1860",
        "Bharatiya Nyaya Sanhita, 2023",
        "bprd-ipc-bns.pdf",
    ),
    TransitionSpec(
        "crpc_bnss",
        LawAct.CRPC,
        LawAct.BNSS,
        "Code of Criminal Procedure, 1973",
        "Bharatiya Nagarik Suraksha Sanhita, 2023",
        "bprd-crpc-bnss.pdf",
    ),
    TransitionSpec(
        "iea_bsa",
        LawAct.IEA,
        LawAct.BSA,
        "Indian Evidence Act, 1872",
        "Bharatiya Sakshya Adhiniyam, 2023",
        "bprd-iea-bsa.pdf",
    ),
)

#: A section number as the tables print it: digits with an optional letter.
SECTION_RE: Final = re.compile(r"^\s*(\d{1,3}[A-Za-z]{0,2})\s*$")

#: Wording the tables use when a provision has no counterpart in the new code.
NO_EQUIVALENT_MARKERS: Final = ("omitted", "deleted", "no corresponding", "not carried", "--", "—")

MIN_COLUMNS: Final = 3


@dataclass(frozen=True, slots=True)
class Row:
    """One extracted table row, before it becomes a mapping."""

    old_section: str
    old_title: str
    new_sections: tuple[str, ...]
    new_title: str
    note: str
    page: int


def extract_rows(pdf_path: Path) -> list[Row]:
    """Pull the table rows out of one correspondence PDF.

    Args:
        pdf_path: The official PDF.

    Returns:
        The rows that parsed cleanly. Anything ambiguous is skipped and
        counted, because a smaller verified set is worth more than a larger
        guessed one.
    """
    import pdfplumber  # noqa: PLC0415 - only needed when the script actually runs

    rows: list[Row] = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_number, page in enumerate(pdf.pages, start=1):
            for table in page.extract_tables() or []:
                rows.extend(_rows_from_table(table, page_number))
    return rows


def _rows_from_table(table: list[list[str | None]], page: int) -> list[Row]:
    """Convert one extracted table into rows, skipping what does not parse."""
    parsed: list[Row] = []
    for raw in table:
        cells = [(cell or "").strip().replace("\n", " ") for cell in raw]
        if len(cells) < MIN_COLUMNS:
            continue
        old_match = SECTION_RE.match(cells[0])
        if old_match is None:
            continue
        parsed.append(
            Row(
                old_section=old_match.group(1),
                old_title=cells[1],
                new_sections=_parse_sections(cells[2]),
                new_title=cells[3] if len(cells) > MIN_COLUMNS else "",
                note=cells[4] if len(cells) > MIN_COLUMNS + 1 else "",
                page=page,
            )
        )
    return parsed


def _parse_sections(cell: str) -> tuple[str, ...]:
    """Read the new-code sections out of one cell, which may list several."""
    if any(marker in cell.casefold() for marker in NO_EQUIVALENT_MARKERS):
        return ()
    return tuple(
        match.group(1)
        for piece in re.split(r"[,/&]|\band\b", cell)
        if (match := SECTION_RE.match(piece.strip()))
    )


def classify(row: Row) -> ChangeType:
    """Decide how an old provision relates to the new code.

    Args:
        row: One extracted row.

    Returns:
        The change type the row's own shape implies. This is arithmetic on the
        extracted cells, never a judgement about the law.
    """
    if not row.new_sections:
        return ChangeType.NO_DIRECT_EQUIVALENT
    if len(row.new_sections) > 1:
        return ChangeType.SPLIT
    if row.note and "merg" in row.note.casefold():
        return ChangeType.MERGED
    if row.note and any(word in row.note.casefold() for word in ("modif", "amend", "chang")):
        return ChangeType.MODIFIED
    return ChangeType.RENUMBERED


def build_transition(spec: TransitionSpec, rows: list[Row]) -> LawTransition:
    """Turn extracted rows into a validated transition.

    Args:
        spec: Which acts these rows map between.
        rows: The extracted rows.

    Returns:
        The transition, every row marked ``extracted``.
    """
    mappings = [
        LawMapping(
            old=ProvisionRef(act=spec.old_act, section=row.old_section, title=row.old_title),
            new=[
                ProvisionRef(act=spec.new_act, section=section, title=row.new_title)
                for section in row.new_sections
            ],
            change_type=classify(row),
            note=row.note,
            source=Source(document=f"BPR&D correspondence table: {spec.filename}", page=row.page),
        )
        for row in rows
    ]
    return LawTransition(
        id=spec.id,
        old_act=spec.old_act,
        new_act=spec.new_act,
        old_act_name=spec.old_name,
        new_act_name=spec.new_name,
        in_force_from=IN_FORCE_FROM,
        source_note=SOURCE_NOTE,
        mappings=_deduplicate(mappings),
    )


def _deduplicate(mappings: list[LawMapping]) -> list[LawMapping]:
    """Keep the first row for each old section, since ids must be unique."""
    seen: dict[str, LawMapping] = {}
    for mapping in mappings:
        seen.setdefault(mapping.old.key, mapping)
    return list(seen.values())


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
        rows = extract_rows(source)
        transition = build_transition(spec, rows)
        path = write(transition, dry_run=arguments.dry_run)
        action = "would write" if arguments.dry_run else "wrote"
        print(
            f"{action} {path.name}: {len(transition.mappings)} rows "
            f"from {len(rows)} extracted, all marked 'extracted' pending review"
        )

    print("\nNext: check each row against its source page, then set review_status")
    print("to 'verified' and add verified_on. See docs/DATA.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
