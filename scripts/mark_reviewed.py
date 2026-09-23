#!/usr/bin/env python3
"""Mark packaged law rows as reviewed.

This does not check anything: it records that a person has, against the source
each row cites, and sets ``review_status`` to ``verified`` with today's date. It
exists so that review is a deliberate, auditable step separate from extraction,
not something a build script can do to itself.

Usage:
    python scripts/mark_reviewed.py --mappings --texts
    python scripts/mark_reviewed.py --mappings --only ipc_bns
    python scripts/mark_reviewed.py --texts --only ipc
    python scripts/mark_reviewed.py --mappings --texts --dry-run
"""

from __future__ import annotations

import argparse
import datetime
import json
import sys
from pathlib import Path
from typing import Final

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.domain.enums import ReviewStatus  # noqa: E402
from app.domain.laws.models import LawMapping, LawTransition, Provision  # noqa: E402

MAPPINGS_DIR: Final = PROJECT_ROOT / "app" / "data" / "laws" / "mappings"
TEXTS_DIR: Final = PROJECT_ROOT / "app" / "data" / "laws" / "texts"


def _mark_mapping(mapping: LawMapping, today: str) -> LawMapping:
    """Return a mapping with its review status set to verified."""
    if mapping.review_status is ReviewStatus.VERIFIED:
        return mapping
    return mapping.model_copy(update={"review_status": ReviewStatus.VERIFIED, "verified_on": today})


def mark_mappings(*, only: str, today: str, dry_run: bool) -> None:
    """Mark every mapping row in every transition file as verified."""
    for path in sorted(MAPPINGS_DIR.glob("*.json")):
        if only and path.stem != only:
            continue
        transition = LawTransition.model_validate(json.loads(path.read_text(encoding="utf-8")))
        before = sum(1 for m in transition.mappings if m.review_status is ReviewStatus.VERIFIED)
        updated = transition.model_copy(
            update={"mappings": [_mark_mapping(m, today) for m in transition.mappings]}
        )
        after = sum(1 for m in updated.mappings if m.review_status is ReviewStatus.VERIFIED)
        if not dry_run:
            payload = updated.model_dump(mode="json", exclude_none=True)
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        action = "would mark" if dry_run else "marked"
        print(
            f"{action} {path.name}: {after - before} of {len(updated.mappings)} rows now verified"
        )


def mark_texts(*, only: str, today: str, dry_run: bool) -> None:
    """Mark every provision text file as verified."""
    for path in sorted(TEXTS_DIR.glob("*.json")):
        if only and path.stem != only:
            continue
        provisions = [
            Provision.model_validate(entry)
            for entry in json.loads(path.read_text(encoding="utf-8"))
        ]
        before = sum(1 for p in provisions if p.review_status is ReviewStatus.VERIFIED)
        updated = [
            p
            if p.review_status is ReviewStatus.VERIFIED
            else p.model_copy(update={"review_status": ReviewStatus.VERIFIED, "verified_on": today})
            for p in provisions
        ]
        after = sum(1 for p in updated if p.review_status is ReviewStatus.VERIFIED)
        if not dry_run:
            payload = [p.model_dump(mode="json", exclude_none=True) for p in updated]
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
        action = "would mark" if dry_run else "marked"
        print(f"{action} {path.name}: {after - before} of {len(updated)} rows now verified")


def main() -> int:
    """Mark whichever packaged files the flags select."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mappings", action="store_true", help="mark law-mapping rows.")
    parser.add_argument("--texts", action="store_true", help="mark provision-text rows.")
    parser.add_argument("--only", default="", help="restrict to one file, by its stem.")
    parser.add_argument("--dry-run", action="store_true", help="report without writing.")
    arguments = parser.parse_args()

    if not arguments.mappings and not arguments.texts:
        parser.error("pass --mappings, --texts, or both")

    today = datetime.date.today().isoformat()
    if arguments.mappings:
        mark_mappings(only=arguments.only, today=today, dry_run=arguments.dry_run)
    if arguments.texts:
        mark_texts(only=arguments.only, today=today, dry_run=arguments.dry_run)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
