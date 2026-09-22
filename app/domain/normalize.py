"""Offset-preserving text normalisation.

Quotes returned by a model rarely match a clause byte for byte: whitespace is
re-wrapped, curly quotes become straight ones, OCR turns an en dash into a
hyphen. Comparing normalised forms fixes that, but a highlight has to point at
the *original* characters, so every normalised character keeps the source range
it came from.
"""

import unicodedata
from dataclasses import dataclass
from typing import Final

#: Dropped outright: they are invisible and appear inconsistently after copy-paste.
ZERO_WIDTH: Final[frozenset[str]] = frozenset("\u200b\u200c\u200d\u2060\ufeff\u00ad\u034f")

_QUOTE_FORMS: Final = "‘’‚‛′ʼ`´"
_DOUBLE_QUOTE_FORMS: Final = "“”„‟″«»"
_DASH_FORMS: Final = "‐‑‒–—―−⁃"

#: Devanagari digits, used in Hindi and Marathi documents.
DEVANAGARI_DIGITS: Final = "०१२३४५६७८९"

_TRANSLATIONS: Final[dict[str, str]] = {
    **dict.fromkeys(_QUOTE_FORMS, "'"),
    **dict.fromkeys(_DOUBLE_QUOTE_FORMS, '"'),
    **dict.fromkeys(_DASH_FORMS, "-"),
    **{digit: str(value) for value, digit in enumerate(DEVANAGARI_DIGITS)},
}


@dataclass(frozen=True, slots=True)
class NormalizedText:
    """Normalised text with a map back to the source string.

    Attributes:
        text: The normalised form: NFC, case-folded, whitespace-collapsed.
        starts: For each character of :attr:`text`, where it began in the source.
        ends: For each character of :attr:`text`, where its source range ended.
    """

    text: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]

    def to_source_span(self, start: int, end: int) -> tuple[int, int]:
        """Translate a span of :attr:`text` back to source offsets.

        Args:
            start: Inclusive start index in :attr:`text`.
            end: Exclusive end index in :attr:`text`.

        Returns:
            The matching ``(start, end)`` span in the source string. An empty or
            out-of-range span collapses to ``(0, 0)``.
        """
        if not self.starts or start >= end or start < 0 or end > len(self.text):
            return (0, 0)
        return (self.starts[start], self.ends[end - 1])


def normalize_with_map(text: str) -> NormalizedText:
    """Normalise text while recording where each character came from.

    The source string is assumed to be in NFC already, which ingestion
    guarantees for every clause. NFC is applied again defensively; when that
    changes the string, offsets refer to the NFC form.

    Args:
        text: Source text, normally a clause body.

    Returns:
        The normalised text together with its offset map.
    """
    source = unicodedata.normalize("NFC", text)
    characters: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    space_start = -1
    space_end = -1

    for index, character in enumerate(source):
        if character in ZERO_WIDTH:
            continue
        if character.isspace():
            if space_start < 0:
                space_start = index
            space_end = index + 1
            continue
        if space_start >= 0:
            if characters:  # leading whitespace is dropped, not collapsed
                characters.append(" ")
                starts.append(space_start)
                ends.append(space_end)
            space_start = -1
        for folded in _TRANSLATIONS.get(character, character).casefold():
            characters.append(folded)
            starts.append(index)
            ends.append(index + 1)

    return NormalizedText(text="".join(characters), starts=tuple(starts), ends=tuple(ends))


def normalize(text: str) -> str:
    """Normalise text without building an offset map.

    Args:
        text: Source text.

    Returns:
        The normalised form, equal to ``normalize_with_map(text).text``.
    """
    return normalize_with_map(text).text


def to_nfc(text: str) -> str:
    """Return ``text`` in Unicode NFC, the form every clause is stored in."""
    return unicodedata.normalize("NFC", text)


def devanagari_digits_to_ascii(text: str) -> str:
    """Replace Devanagari digits with ASCII digits, leaving everything else alone."""
    return text.translate({ord(digit): str(value) for value, digit in enumerate(DEVANAGARI_DIGITS)})
