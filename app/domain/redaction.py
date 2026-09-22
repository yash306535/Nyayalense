"""Mask personal identifiers before any text leaves the process.

Aadhaar and PAN numbers, phone numbers and email addresses are replaced in the
clause text itself, so the masked form is what reaches a model, a log or an
export. A twelve-digit string is only treated as an Aadhaar number when it
passes the Verhoeff checksum, which keeps invoice and account numbers readable.
"""

import re
from dataclasses import dataclass
from typing import Final

from app.domain.enums import IdentifierKind
from app.domain.normalize import devanagari_digits_to_ascii

#: Multiplication table of the dihedral group D5, used by the Verhoeff checksum.
_D5_MULTIPLY: Final[tuple[tuple[int, ...], ...]] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 2, 3, 4, 0, 6, 7, 8, 9, 5),
    (2, 3, 4, 0, 1, 7, 8, 9, 5, 6),
    (3, 4, 0, 1, 2, 8, 9, 5, 6, 7),
    (4, 0, 1, 2, 3, 9, 5, 6, 7, 8),
    (5, 9, 8, 7, 6, 0, 4, 3, 2, 1),
    (6, 5, 9, 8, 7, 1, 0, 4, 3, 2),
    (7, 6, 5, 9, 8, 2, 1, 0, 4, 3),
    (8, 7, 6, 5, 9, 3, 2, 1, 0, 4),
    (9, 8, 7, 6, 5, 4, 3, 2, 1, 0),
)

#: Permutation applied once per position, repeating with period 8.
_PERMUTE: Final[tuple[tuple[int, ...], ...]] = (
    (0, 1, 2, 3, 4, 5, 6, 7, 8, 9),
    (1, 5, 7, 6, 2, 8, 3, 0, 9, 4),
    (5, 8, 0, 3, 7, 9, 6, 1, 4, 2),
    (8, 9, 1, 6, 0, 4, 3, 5, 2, 7),
    (9, 4, 5, 3, 1, 2, 6, 8, 7, 0),
    (4, 2, 8, 6, 5, 7, 3, 9, 0, 1),
    (2, 7, 9, 3, 8, 0, 6, 4, 1, 5),
    (7, 0, 4, 6, 9, 1, 3, 2, 5, 8),
)

AADHAAR_LENGTH: Final = 12

#: Twelve digits in three groups, first digit 2-9, separated by spaces or hyphens.
_AADHAAR_RE: Final = re.compile(r"(?<!\d)([2-9]\d{3})[\s-]?(\d{4})[\s-]?(\d{4})(?!\d)")

#: Five letters, four digits, one letter.
_PAN_RE: Final = re.compile(r"(?<![A-Z0-9])([A-Z]{5}\d{4}[A-Z])(?![A-Z0-9])")

#: Indian mobile numbers, optionally with a country code or a leading zero.
_PHONE_RE: Final = re.compile(r"(?<![\d+])(?:\+91[\s-]?|0)?([6-9]\d{4}[\s-]?\d{5})(?!\d)")

_EMAIL_RE: Final = re.compile(r"(?<![\w.+-])[\w.+-]+@[\w-]+(?:\.[\w-]+)+(?![\w-])")

MASKS: Final[dict[IdentifierKind, str]] = {
    IdentifierKind.AADHAAR: "[AADHAAR HIDDEN]",
    IdentifierKind.PAN: "[PAN HIDDEN]",
    IdentifierKind.PHONE: "[PHONE HIDDEN]",
    IdentifierKind.EMAIL: "[EMAIL HIDDEN]",
}


@dataclass(frozen=True, slots=True)
class MaskingResult:
    """Masked text and a tally of what was hidden.

    Attributes:
        text: The text with every identifier replaced by its label.
        counts: How many of each kind were replaced.
    """

    text: str
    counts: dict[IdentifierKind, int]

    @property
    def total(self) -> int:
        """How many identifiers were hidden in all."""
        return sum(self.counts.values())


def verhoeff_is_valid(digits: str) -> bool:
    """Check a digit string against the Verhoeff checksum.

    Aadhaar numbers carry a Verhoeff check digit. Requiring it turns a
    twelve-digit pattern into a test with roughly a one-in-ten false-positive
    rate, so ordinary reference numbers are left alone.

    Args:
        digits: A string of ASCII digits, check digit last.

    Returns:
        True when the checksum is satisfied.
    """
    if not digits.isdigit():
        return False
    checksum = 0
    for position, character in enumerate(reversed(digits)):
        checksum = _D5_MULTIPLY[checksum][_PERMUTE[position % 8][int(character)]]
    return checksum == 0


def _mask_aadhaar(text: str, counts: dict[IdentifierKind, int]) -> str:
    """Replace valid Aadhaar numbers, leaving lookalikes in place."""

    def replace(match: re.Match[str]) -> str:
        digits = "".join(match.groups())
        if not verhoeff_is_valid(digits):
            return match.group(0)
        counts[IdentifierKind.AADHAAR] = counts.get(IdentifierKind.AADHAAR, 0) + 1
        return MASKS[IdentifierKind.AADHAAR]

    return _AADHAAR_RE.sub(replace, text)


def _mask_pattern(
    text: str, pattern: re.Pattern[str], kind: IdentifierKind, counts: dict[IdentifierKind, int]
) -> str:
    """Replace every match of ``pattern`` with the mask for ``kind``."""

    def replace(_: re.Match[str]) -> str:
        counts[kind] = counts.get(kind, 0) + 1
        return MASKS[kind]

    return pattern.sub(replace, text)


def mask_identifiers(text: str) -> MaskingResult:
    """Hide every personal identifier in the text.

    Email addresses are masked first so that digits inside an address are never
    mistaken for a phone number. Aadhaar comes before phone numbers for the same
    reason.

    Args:
        text: Text to mask, typically one clause.

    Returns:
        The masked text and the counts by kind.
    """
    counts: dict[IdentifierKind, int] = {}
    masked = devanagari_digits_to_ascii(text)
    masked = _mask_pattern(masked, _EMAIL_RE, IdentifierKind.EMAIL, counts)
    masked = _mask_aadhaar(masked, counts)
    masked = _mask_pattern(masked, _PAN_RE, IdentifierKind.PAN, counts)
    masked = _mask_pattern(masked, _PHONE_RE, IdentifierKind.PHONE, counts)
    return MaskingResult(text=masked, counts=counts)


def describe_masking(counts: dict[IdentifierKind, int], *, labels: dict[str, str]) -> str:
    """Build the sentence shown to the user after ingestion.

    Args:
        counts: How many identifiers of each kind were hidden.
        labels: Singular and plural names per kind, keyed ``"<kind>"`` and
            ``"<kind>_plural"``.

    Returns:
        A sentence such as ``"2 Aadhaar numbers and 1 phone number were hidden
        before analysis."``, or an empty string when nothing was hidden. The
        verb agrees with the total, so a lone identifier reads correctly too.
    """
    if not counts:
        return ""
    parts = [
        f"{count} {labels[kind.value if count == 1 else f'{kind.value}_plural']}"
        for kind, count in sorted(counts.items(), key=lambda item: item[0].value)
    ]
    listed = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    verb = "was" if sum(counts.values()) == 1 else "were"
    return f"{listed} {verb} hidden before analysis."
