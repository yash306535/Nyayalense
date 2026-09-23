#!/usr/bin/env python3
"""Build the packaged provision texts from India Code.

Where the text comes from depends on the act, because India Code publishes the
two generations of code differently:

* **The new codes** (BNS, BNSS, BSA) have one published record per section, with
  the text in a field of that record. Those are read over India Code's own REST
  API, one request per hundred sections.
* **The codes they replaced** are no longer published that way. Since their
  repeal on 1 July 2024, India Code keeps the Indian Penal Code and the Indian
  Evidence Act only as the consolidated act PDF on their repeal entry. Download
  those two PDFs into ``data_sources/`` (see its README) and this script reads
  the sections out of them.

**The Code of Criminal Procedure is not built here.** The only copy India Code
now publishes is a scan of the 1974 gazette whose text layer is too degraded to
quote from -- it reads ``Code ot Criminai .Procedure`` on its own running head.
Quoting that at a user would break the one promise this application makes, so
CrPC sections ship with no stored text and the interface says so. Sections of
the BNSS that replaced them are built as usual, from the API.

No search engine, no third-party index, and no model is involved at any point.
Nothing here rewrites what India Code published: the readers drop the watermark
and the page furniture, and leave the words alone.

Every row is written ``extracted``. A person must read it against the source and
mark it ``verified`` before users see it. See ``docs/DATA.md``.

Usage:
    python scripts/build_provision_texts.py [--dry-run] [--only ipc]
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

from app.domain.enums import LawAct  # noqa: E402
from app.domain.laws.models import Provision, Source  # noqa: E402

from scripts.indiacode import (  # noqa: E402
    ExtractedSection,
    api,
    consolidated,
)

SOURCE_DIR: Final = PROJECT_ROOT / "data_sources"
OUTPUT_DIR: Final = PROJECT_ROOT / "app" / "data" / "laws" / "texts"

#: The schema's ceilings. A section that does not fit is left out rather than
#: cut short: half a provision reads like the whole one and would mislead.
MAX_TITLE_CHARS: Final = 500
MAX_TEXT_CHARS: Final = 20_000

#: What a section number may look like, matching the schema.
SECTION_PATTERN: Final = "^[0-9]{1,3}[A-Za-z]{0,2}$"


@dataclass(frozen=True, slots=True)
class ActSpec:
    """One act and where its text is read from.

    Attributes:
        act: Which code this is.
        source_name: The act's name as India Code records it, for API acts.
        filename: The PDF in ``data_sources/``, for PDF acts.
        url: The India Code page a reviewer checks the text against.
        document: What to record as the source of every row.
    """

    act: LawAct
    url: str
    document: str
    source_name: str = ""
    filename: str = ""


SPECS: Final[tuple[ActSpec, ...]] = (
    ActSpec(
        act=LawAct.IPC,
        filename="indiacode-ipc.pdf",
        url="https://indiacode.gov.in/handle/123456789/488475",
        document="India Code consolidated text of the repealed Act: indiacode-ipc.pdf",
    ),
    ActSpec(
        act=LawAct.IEA,
        filename="indiacode-iea.pdf",
        url="https://indiacode.gov.in/handle/123456789/488783",
        document="India Code consolidated text of the repealed Act: indiacode-iea.pdf",
    ),
    ActSpec(
        act=LawAct.BNS,
        source_name="The Bharatiya Nyaya Sanhita, 2023",
        url="https://indiacode.gov.in/handle/123456789/496548",
        document="India Code section record (indiacode.gov.in)",
    ),
    ActSpec(
        act=LawAct.BNSS,
        source_name="The Bharatiya Nagarik Suraksha Sanhita, 2023",
        url="https://indiacode.gov.in/handle/123456789/496550",
        document="India Code section record (indiacode.gov.in)",
    ),
    ActSpec(
        act=LawAct.BSA,
        source_name="The Bharatiya Sakshya Adhiniyam, 2023",
        url="https://indiacode.gov.in/handle/123456789/496549",
        document="India Code section record (indiacode.gov.in)",
    ),
)


@dataclass(frozen=True, slots=True)
class BuildReport:
    """What one act's build produced.

    Attributes:
        provisions: The rows that will be written.
        left_out: One line per section that could not be written, and why.
    """

    provisions: list[Provision]
    left_out: list[str]


def to_provision(section: ExtractedSection, spec: ActSpec) -> Provision | None:
    """Turn one extracted section into a packaged row.

    Args:
        section: What the reader found.
        spec: The act it belongs to.

    Returns:
        The row, or ``None`` when it does not fit the schema. Nothing is cut
        short to make it fit.
    """
    if not re.match(SECTION_PATTERN, section.section):
        return None
    if not section.title or len(section.title) > MAX_TITLE_CHARS:
        return None
    if not section.text or len(section.text) > MAX_TEXT_CHARS:
        return None
    return Provision(
        act=spec.act,
        section=section.section,
        title=section.title,
        text=section.text,
        source=Source(document=spec.document, page=section.page, url=section.url or spec.url),
    )


def build(spec: ActSpec, sections: list[ExtractedSection]) -> BuildReport:
    """Turn one act's sections into validated rows.

    Args:
        spec: The act being built.
        sections: What its reader found.

    Returns:
        The rows, and a line for each section left out.
    """
    provisions, left_out = [], []
    for section in sorted(sections, key=_sort_key):
        provision = to_provision(section, spec)
        if provision is None:
            left_out.append(
                f"{spec.act.value} {section.section}: "
                f"title {len(section.title)} chars, text {len(section.text)} chars"
            )
        else:
            provisions.append(provision)
    return BuildReport(provisions=provisions, left_out=left_out)


def _sort_key(section: ExtractedSection) -> tuple[int, str]:
    """Order sections the way the act does: 1, 2, 2A, 3."""
    digits = "".join(character for character in section.section if character.isdigit())
    letters = "".join(character for character in section.section if character.isalpha())
    return int(digits or 0), letters


def read(spec: ActSpec) -> tuple[list[ExtractedSection], list[str]]:
    """Read one act from whichever source publishes it.

    Args:
        spec: The act to read.

    Returns:
        Its sections, and a note for anything the reader could not place.
    """
    if spec.filename:
        readout = consolidated.extract(SOURCE_DIR / spec.filename, url=spec.url)
        notes = [f"{len(readout.untitled)} repealed or omitted sections carry no text"]
        if readout.repeated:
            notes.append(f"printed more than once, first kept: {', '.join(readout.repeated)}")
        return readout.sections, notes
    feed = api.fetch(spec.source_name)
    notes = [f"{len(feed.skipped)} records held no section text"] if feed.skipped else []
    return feed.sections, notes


def write(spec: ActSpec, provisions: list[Provision], *, dry_run: bool) -> Path:
    """Write one act's text file.

    Args:
        spec: The act being written.
        provisions: Its validated rows.
        dry_run: When true, report what would be written and change nothing.

    Returns:
        The path that was written, or would have been.
    """
    path = OUTPUT_DIR / f"{spec.act.value}.json"
    if dry_run:
        return path
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    payload = [provision.model_dump(mode="json", exclude_none=True) for provision in provisions]
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    """Build every act's text file that can be built."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="report without writing.")
    parser.add_argument("--only", default="", help="build one act, by its short name.")
    arguments = parser.parse_args()

    selected = [spec for spec in SPECS if spec.act.value == arguments.only or not arguments.only]
    if not selected:
        print(f"No act called {arguments.only!r}. Known: {[s.act.value for s in SPECS]}")
        return 1

    for spec in selected:
        if spec.filename and not (SOURCE_DIR / spec.filename).exists():
            print(f"skipped {spec.act.value}: {spec.filename} is not in data_sources/")
            continue
        sections, notes = read(spec)
        report = build(spec, sections)
        path = write(spec, report.provisions, dry_run=arguments.dry_run)
        action = "would write" if arguments.dry_run else "wrote"
        print(f"{action} {path.name}: {len(report.provisions)} sections, all marked 'extracted'")
        for note in notes:
            print(f"    note: {note}")
        for line in report.left_out:
            print(f"    left out: {line}")

    print("\nThe Code of Criminal Procedure is not built: the only copy India Code")
    print("still publishes is a gazette scan too degraded to quote from. CrPC")
    print("sections have no stored text, and the interface says so.")
    print("\nNext: read each row against its source, then set review_status to")
    print("'verified' and add verified_on. See docs/DATA.md.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
