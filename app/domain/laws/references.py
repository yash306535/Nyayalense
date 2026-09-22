"""Parse citations to Indian criminal-law provisions.

People write the same reference a dozen ways: ``IPC 420``, ``420 IPC``,
``Section 420 of the Indian Penal Code``, ``u/s 420``, ``धारा 420 भा.दं.सं.``.
Recognising them is pure pattern matching, so a search box and a document scan
can share one parser, and the result never depends on a model's memory.
"""

import re
from typing import Final

from app.domain.enums import LawAct
from app.domain.laws.models import LawReference
from app.domain.normalize import devanagari_digits_to_ascii

#: Short forms. A bare abbreviation next to a number is reference enough.
_ABBREVIATIONS: Final[dict[str, LawAct]] = {
    "ipc": LawAct.IPC,
    "i.p.c.": LawAct.IPC,
    "i p c": LawAct.IPC,
    "crpc": LawAct.CRPC,
    "cr.p.c.": LawAct.CRPC,
    "cr. p.c.": LawAct.CRPC,
    "cr.p.c": LawAct.CRPC,
    "crpc.": LawAct.CRPC,
    "c.r.p.c.": LawAct.CRPC,
    "iea": LawAct.IEA,
    "i.e.a.": LawAct.IEA,
    "bns": LawAct.BNS,
    "b.n.s.": LawAct.BNS,
    "bnss": LawAct.BNSS,
    "b.n.s.s.": LawAct.BNSS,
    "bsa": LawAct.BSA,
    "b.s.a.": LawAct.BSA,
    "भा.दं.सं.": LawAct.IPC,
    "भादंसं": LawAct.IPC,
    "भादंवि": LawAct.IPC,
    "भा.द.वि.": LawAct.IPC,
    "दं.प्र.सं.": LawAct.CRPC,
    "दंप्रसं": LawAct.CRPC,
    "फौ.प्र.सं.": LawAct.CRPC,
    "भा.सा.अ.": LawAct.IEA,
    "भा.न्या.सं.": LawAct.BNS,
    "भान्यासं": LawAct.BNS,
    "भा.ना.सु.सं.": LawAct.BNSS,
}

#: Full names. These need an explicit section marker to count as a reference.
_FULL_NAMES: Final[dict[str, LawAct]] = {
    "indian penal code": LawAct.IPC,
    "penal code": LawAct.IPC,
    "भारतीय दंड संहिता": LawAct.IPC,
    "भारतीय दण्ड संहिता": LawAct.IPC,
    "code of criminal procedure": LawAct.CRPC,
    "criminal procedure code": LawAct.CRPC,
    "फौजदारी प्रक्रिया संहिता": LawAct.CRPC,
    "दंड प्रक्रिया संहिता": LawAct.CRPC,
    "indian evidence act": LawAct.IEA,
    "evidence act": LawAct.IEA,
    "भारतीय साक्ष्य अधिनियम": LawAct.IEA,
    "साक्ष्य अधिनियम": LawAct.IEA,
    "bharatiya nyaya sanhita": LawAct.BNS,
    "भारतीय न्याय संहिता": LawAct.BNS,
    "bharatiya nagarik suraksha sanhita": LawAct.BNSS,
    "भारतीय नागरिक सुरक्षा संहिता": LawAct.BNSS,
    "bharatiya sakshya adhiniyam": LawAct.BSA,
    "भारतीय साक्ष्य संहिता": LawAct.BSA,
}

#: ``Evidence Act`` and ``भारतीय साक्ष्य अधिनियम`` name both evidence acts. The
#: year beside the name decides which is meant; without a year the older act is
#: assumed, because that is the reference a user needs translated.
_BSA_YEAR: Final = "2023"
_AMBIGUOUS_EVIDENCE_NAMES: Final = (
    "साक्ष्य अधिनियम",
    "भारतीय साक्ष्य अधिनियम",
    "evidence act",
    "indian evidence act",
)

#: Where an act name is followed by its year, that year is not a section number.
_YEARS: Final = ("1860", "1872", "1973", "2023")

_MARKERS: Final = (
    "under sections",
    "under section",
    "u/ss",
    "u/s",
    "sections",
    "section",
    "secs.",
    "sec.",
    "ss.",
    "s.",
    "धाराओं",
    "धारा",
    "कलमे",
    "कलम",
    "अनुच्छेद",
)

_SECTION = r"(?<!\d)\d{1,3}[A-Za-z]{0,2}(?!\d)(?:\s*\(\s*[0-9A-Za-z]{1,3}\s*\))?"
_SECTION_LIST = rf"{_SECTION}(?:\s*(?:,|and|&|/|तथा|और|व)\s*{_SECTION})*"
_MARKER = "(?:" + "|".join(re.escape(marker) for marker in _MARKERS) + ")"


def _alternation(names: dict[str, LawAct]) -> str:
    """Build a regex alternation over act names, longest first."""
    ordered = sorted(names, key=len, reverse=True)
    return "(?:" + "|".join(re.escape(name) for name in ordered) + ")"


_ABBR_ALT: Final = _alternation(_ABBREVIATIONS)
_FULL_ALT: Final = _alternation(_FULL_NAMES)
_ANY_ALT: Final = _alternation({**_ABBREVIATIONS, **_FULL_NAMES})

#: ``Section 420 of the Indian Penal Code``, ``420 IPC``, ``u/s 154 Cr.P.C.``
_SECTION_FIRST: Final = re.compile(
    rf"(?:(?P<marker>{_MARKER})\s*)?(?P<sections>{_SECTION_LIST})\s*"
    rf"(?:,\s*)?(?:of\s+(?:the\s+)?|under\s+(?:the\s+)?|र्‍या\s+)?"
    rf"(?P<act>{_ANY_ALT})",
    re.IGNORECASE,
)

#: What may sit between an act name and the section it introduces: the act's
#: year, and the genitive particle Hindi and Marathi put there.
_LINK: Final = r"\s*,?\s*(?:" + "|".join(_YEARS) + r")?\s*,?\s*(?:की|के|का|चा|च्या|ची|of|under)?\s*"

#: ``IPC 420``, ``BNS 318(4)`` - a short form needs no marker.
_ABBR_FIRST: Final = re.compile(
    rf"(?P<act>{_ABBR_ALT}){_LINK}(?:(?P<marker>{_MARKER})\s*)?(?P<sections>{_SECTION_LIST})",
    re.IGNORECASE,
)

#: ``भादंवि कलम 420``, ``Indian Penal Code, Section 420`` - a full name needs one.
_FULL_FIRST: Final = re.compile(
    rf"(?P<act>{_FULL_ALT}){_LINK}(?P<marker>{_MARKER})\s*(?P<sections>{_SECTION_LIST})",
    re.IGNORECASE,
)

_PATTERNS: Final = (_SECTION_FIRST, _ABBR_FIRST, _FULL_FIRST)

_SPLIT_SECTIONS: Final = re.compile(r"\s*(?:,|and|&|/|तथा|और|व)\s*", re.IGNORECASE)
_SPLIT_PARTS: Final = re.compile(
    r"^(?P<section>\d{1,3}[A-Za-z]{0,2})(?:\s*\(\s*(?P<sub>[0-9A-Za-z]{1,3})\s*\))?$"
)


def _resolve_act(name: str, text: str, position: int) -> LawAct | None:
    """Map a matched act name to an act, disambiguating the evidence acts."""
    key = name.casefold().strip()
    act = _ABBREVIATIONS.get(key) or _FULL_NAMES.get(key)
    if act is None:
        return None
    if act is LawAct.IEA and any(key.endswith(name) for name in _AMBIGUOUS_EVIDENCE_NAMES):
        window = text[position : position + len(name) + 12]
        if _BSA_YEAR in window:
            return LawAct.BSA
    return act


def _parse_sections(blob: str) -> list[tuple[str, str]]:
    """Split a section list into ``(section, subsection)`` pairs."""
    parsed: list[tuple[str, str]] = []
    for piece in _SPLIT_SECTIONS.split(blob.strip()):
        match = _SPLIT_PARTS.match(piece.strip())
        if match is None or match.group("section") in _YEARS:
            continue
        parsed.append((match.group("section"), match.group("sub") or ""))
    return parsed


def find_references(text: str) -> list[LawReference]:
    """Find every statutory reference in a piece of text.

    Args:
        text: Any text: a clause, a whole document, or a search query.

    Returns:
        The references found, in order of appearance. Where two patterns match
        the same reference, it appears once.
    """
    source = devanagari_digits_to_ascii(text)
    candidates: list[LawReference] = []

    for pattern in _PATTERNS:
        for match in pattern.finditer(source):
            act = _resolve_act(match.group("act"), source, match.start("act"))
            if act is None:  # pragma: no cover - the alternation only matches known names
                continue
            candidates.extend(
                LawReference(
                    act=act,
                    section=section,
                    subsection=subsection,
                    raw=match.group(0).strip(),
                    start=match.start(),
                    end=match.end(),
                )
                for section, subsection in _parse_sections(match.group("sections"))
            )

    return _dedupe(candidates)


def _dedupe(candidates: list[LawReference]) -> list[LawReference]:
    """Drop repeats of the same reference found by more than one pattern.

    Two hits are the same reference when they name the same provision and their
    matched spans overlap. The same section cited twice in different places
    stays twice, because each is its own occurrence in the document.

    Args:
        candidates: Every hit from every pattern.

    Returns:
        The distinct references, in document order.
    """
    kept: list[LawReference] = []
    for reference in sorted(candidates, key=lambda ref: (ref.start, -(ref.end - ref.start))):
        if any(_is_repeat(reference, existing) for existing in kept):
            continue
        kept.append(reference)
    return sorted(kept, key=lambda ref: (ref.start, ref.section))


def _is_repeat(reference: LawReference, existing: LawReference) -> bool:
    """True when two hits name the same provision over overlapping text."""
    return (
        existing.act is reference.act
        and existing.section == reference.section
        and existing.subsection == reference.subsection
        and reference.start < existing.end
        and existing.start < reference.end
    )


def parse_query(query: str) -> LawReference | None:
    """Parse a user's search box input into a single reference.

    Args:
        query: What the user typed, such as ``"S. 65B Evidence Act"``.

    Returns:
        The first reference found, or ``None`` when the query names no act.
    """
    references = find_references(query)
    return references[0] if references else None
