"""Extract the terms a document defines for itself.

A contract that redefines an ordinary word is where misunderstandings start.
Finding those definitions is pattern matching, not reasoning, so no model is
involved and the glossary can always prefer the document's own wording over a
general one.
"""

import re
from typing import Final

from app.domain.models import Clause, DefinedTerm

#: Abbreviations whose full stop does not end a sentence. Without these,
#: ``Rs. 5,000`` and ``Mr. A. Kulkarni`` would cut a definition in half.
_NOT_A_SENTENCE_END: Final = (
    "".join(
        rf"(?<!\b{abbreviation})"
        for abbreviation in ("Rs", "Mr", "Mrs", "Ms", "Dr", "No", "Co", "Ltd", "Pvt", "Sr", "Jr")
    )
    + r"(?<!\s\w)"
)  # a lone initial, as in "A."

#: A full stop or semicolon that really does end a sentence.
_SENTENCE_STOP: Final = rf"{_NOT_A_SENTENCE_END}[.;]"

_SENTENCE_END_RE: Final = re.compile(rf"{_SENTENCE_STOP}\s", re.IGNORECASE)

#: Longest definition body the patterns will read. A definition longer than this
#: is skipped rather than truncated: a half-quoted definition would mislead.
MAX_DEFINITION_BODY: Final = 600

#: Quoted term followed by a defining verb: "Premises" means Flat 7B.
_QUOTED_DEFINITION_RE: Final = re.compile(
    r"[\"'“‘]\s*(?P<term>[^\"'”’]{1,80}?)\s*[\"'”’]\s*"
    r"(?:shall\s+mean|means|shall\s+have\s+the\s+meaning|refers\s+to)\s*"
    rf"(?P<body>.{{1,{MAX_DEFINITION_BODY}}}?)(?={_SENTENCE_STOP}(?:\s|$)|\Z)",
    re.IGNORECASE | re.DOTALL,
)

#: Trailing label: ... (hereinafter referred to as the "Licensee").
_HEREINAFTER_RE: Final = re.compile(
    r"hereinafter\s+(?:referred\s+to\s+as|called)\s+(?:the\s+)?"
    r"[\"'“‘]?\s*(?P<term>[^\"'”’)]{1,80}?)\s*[\"'”’]?\s*\)",
    re.IGNORECASE,
)

#: Unquoted definition line: Premises means Flat 7B.
_PLAIN_DEFINITION_RE: Final = re.compile(
    rf"^(?P<term>[A-Z][\w -]{{1,60}}?)\s+(?:shall\s+mean|means)\s+"
    rf"(?P<body>.{{1,{MAX_DEFINITION_BODY}}}?)(?={_SENTENCE_STOP}(?:\s|$)|\Z)",
    re.DOTALL,
)


MAX_DEFINITION_CHARS: Final = 300


def _first_sentence(text: str) -> str:
    """Trim a definition body to its first sentence, within the length limit."""
    match = _SENTENCE_END_RE.search(text)
    body = text[: match.start() + 1] if match else text
    return body.strip()[:MAX_DEFINITION_CHARS].strip()


def _last_sentence(text: str) -> str:
    """Return the sentence a trailing label belongs to.

    ``... of Pune. Mr. A. Kulkarni (hereinafter the "Licensor")`` defines the
    Licensor as the name just before the bracket, not as the opening words of
    the clause.
    """
    pieces = [piece for piece in _SENTENCE_END_RE.split(text) if piece.strip()]
    tail = pieces[-1] if pieces else text
    return tail.strip().rstrip("(").strip()[-MAX_DEFINITION_CHARS:].strip()


def extract_defined_terms(clauses: list[Clause]) -> list[DefinedTerm]:
    """Find every term the document defines.

    Args:
        clauses: The document's clause map.

    Returns:
        One entry per distinct term, in document order. The first definition of
        a term wins, which matches how a definitions clause is meant to read.
    """
    found: dict[str, DefinedTerm] = {}

    for clause in clauses:
        for term, body in _definitions_in(clause.text):
            key = term.casefold()
            if key in found or not body:
                continue
            found[key] = DefinedTerm(term=term, definition=body, clause_id=clause.id)

    return list(found.values())


def _definitions_in(text: str) -> list[tuple[str, str]]:
    """Return ``(term, definition)`` pairs found in one clause."""
    pairs: list[tuple[str, str]] = []

    for match in _QUOTED_DEFINITION_RE.finditer(text):
        pairs.append((match.group("term").strip(), _first_sentence(match.group("body"))))

    for match in _HEREINAFTER_RE.finditer(text):
        term = match.group("term").strip()
        pairs.append((term, _last_sentence(text[: match.start()])))

    plain = _PLAIN_DEFINITION_RE.match(text.strip())
    if plain is not None:
        pairs.append((plain.group("term").strip(), _first_sentence(plain.group("body"))))

    return [(term, body) for term, body in pairs if term and not term.isspace()]
