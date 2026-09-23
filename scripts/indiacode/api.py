"""Read section texts from India Code's own REST API.

India Code runs DSpace, and publishes each section of the new codes as its own
record. One of that record's fields holds the section's text as a fragment of
presentational HTML: paragraphs separated by ``<br/>``, indents drawn with empty
``<span>`` elements, and italics on labels such as *Explanation*. This module
asks for those records and turns that fragment back into lines of text.

It talks only to indiacode.gov.in -- no search engine, no third-party index, and
no model anywhere near the statutory text.
"""

from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any, Final

from scripts.indiacode.models import ExtractedSection

BASE_URL: Final = "https://indiacode.gov.in"
SEARCH_URL: Final = f"{BASE_URL}/server/api/discover/search/objects"
HANDLE_URL: Final = f"{BASE_URL}/handle/"

#: Says who is asking, so the site's operators can see this is not a crawler.
USER_AGENT: Final = "NyayaLens/1.0 (packaged law data builder; one pass per act)"

#: Records per request. DSpace caps a page at 100.
PAGE_SIZE: Final = 100

REQUEST_TIMEOUT: Final = 60

#: The record fields this reader uses.
FIELD_ACT: Final = "dc.identifier.act_name"
FIELD_SECTION: Final = "dc.identifier.section_number"
FIELD_TEXT: Final = "dc.identifier.section_page_note"
FIELD_PAGE: Final = "dc.identifier.page_number"
FIELD_TITLE: Final = "dc.title"

#: Only these records hold section text; an act also has schedules and notes.
SECTION_COLLECTION: Final = "SECTION"

#: Tags that end a line. Everything else is presentational and is dropped.
BREAK_TAGS: Final = frozenset({"br", "p", "div", "li", "tr"})

WHITESPACE: Final = re.compile(r"[^\S\n]+")


@dataclass(frozen=True, slots=True)
class ApiReadout:
    """Everything one act's records yielded.

    Attributes:
        sections: The sections that carried both a number and text.
        skipped: Titles of records that did not, which are left out.
    """

    sections: list[ExtractedSection]
    skipped: list[str]


class _TextFromMarkup(HTMLParser):
    """Turn India Code's presentational markup back into lines of text."""

    def __init__(self) -> None:
        """Start with nothing collected."""
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """End the current line when the tag is a line break."""
        del attrs
        if tag in BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """End the current line when a block element closes."""
        if tag in BREAK_TAGS - {"br"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        """Keep the text itself, exactly as it was published."""
        self.parts.append(data)


def html_to_text(markup: str) -> str:
    """Turn one section's published markup into plain text.

    Args:
        markup: The value of the record's text field.

    Returns:
        The same words, one line per published paragraph, with runs of spaces
        collapsed and blank lines dropped. No word is added or removed.
    """
    parser = _TextFromMarkup()
    parser.feed(markup)
    parser.close()
    joined = WHITESPACE.sub(" ", "".join(parser.parts))
    return "\n".join(line.strip() for line in joined.split("\n") if line.strip())


def _get(url: str) -> dict[str, Any]:
    """Fetch one JSON document from India Code.

    Args:
        url: The address to read.

    Returns:
        The decoded document.

    Raises:
        ValueError: If the address is not on indiacode.gov.in. The reader is
            deliberately unable to fetch statutory text from anywhere else.
    """
    if not url.startswith(f"{BASE_URL}/"):
        raise ValueError(f"refusing to fetch statutory text from {url!r}")
    request = urllib.request.Request(  # noqa: S310 -- scheme and host checked above
        url, headers={"Accept": "application/json", "User-Agent": USER_AGENT}
    )
    # The scheme and host are fixed by the check above, which is what the
    # scanners are asking about: this cannot be pointed at another source.
    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:  # noqa: S310  # nosec B310
        payload: dict[str, Any] = json.loads(response.read().decode("utf-8"))
    return payload


def _search_url(act_name: str, page: int, size: int) -> str:
    """Build the query for one page of an act's section records."""
    query = f'dc.identifier.collection:{SECTION_COLLECTION} AND {FIELD_ACT}:"{act_name}"'
    parameters = urllib.parse.urlencode({"query": query, "size": size, "page": page})
    return f"{SEARCH_URL}?{parameters}"


def _first(metadata: dict[str, list[dict[str, Any]]], field: str) -> str:
    """Read the first value of a record field, or an empty string."""
    values = metadata.get(field) or []
    return str(values[0]["value"]) if values else ""


def _as_section(record: dict[str, Any], act_name: str) -> ExtractedSection | None:
    """Turn one record into a section, or ``None`` when it is not usable."""
    metadata = record.get("metadata", {})
    if _first(metadata, FIELD_ACT) != act_name:
        return None
    number = _first(metadata, FIELD_SECTION).strip()
    text = html_to_text(_first(metadata, FIELD_TEXT))
    if not number or not text:
        return None
    handle = str(record.get("handle", ""))
    return ExtractedSection(
        section=number,
        title=_first(metadata, FIELD_TITLE).strip(),
        text=text,
        page=int(_first(metadata, FIELD_PAGE) or 0),
        url=f"{HANDLE_URL}{handle}" if handle else "",
    )


def read_page(
    payload: dict[str, Any], act_name: str
) -> tuple[list[ExtractedSection], list[str], int]:
    """Pull the sections out of one page of search results.

    Args:
        payload: A decoded search response.
        act_name: The act whose records are wanted, matched exactly.

    Returns:
        The sections on this page, the titles of records left out, and how many
        pages the whole result has.
    """
    result = payload["_embedded"]["searchResult"]
    sections, skipped = [], []
    for entry in result["_embedded"]["objects"]:
        record = entry["_embedded"]["indexableObject"]
        section = _as_section(record, act_name)
        if section is None:
            skipped.append(str(record.get("name", ""))[:80])
        else:
            sections.append(section)
    return sections, skipped, int(result["page"]["totalPages"])


def fetch(act_name: str, *, size: int = PAGE_SIZE) -> ApiReadout:
    """Read every section record India Code holds for one act.

    Args:
        act_name: The act's name as India Code records it, matched exactly.
        size: Records per request.

    Returns:
        Everything the records yielded.
    """
    sections: list[ExtractedSection] = []
    skipped: list[str] = []
    page, total = 0, 1
    while page < total:
        found, left_out, total = read_page(_get(_search_url(act_name, page, size)), act_name)
        sections.extend(found)
        skipped.extend(left_out)
        page += 1
    return ApiReadout(sections=sections, skipped=skipped)
