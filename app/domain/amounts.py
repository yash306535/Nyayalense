"""Reading Indian numbers, however they are written.

The *figure check* in :mod:`app.domain.verification` needs every number a
statement mentions to appear in a quote, which means comparing values rather
than strings: ``1,50,000``, ``150000`` and ``1.5 lakh`` are one number, and so
is "One Lakh Fifty Thousand".

Comparing the two spellings of one amount against each other, to find a
contract that disagrees with itself, lives in :mod:`app.domain.mismatches`.
"""

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Final

from app.domain.normalize import devanagari_digits_to_ascii

_UNITS: Final[dict[str, int]] = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fourty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}  # fmt: skip

#: Multipliers that close off the part of the number read so far.
_SCALES: Final[dict[str, int]] = {
    "thousand": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
}

_HUNDRED: Final = "hundred"

#: Words that may appear inside a spelled-out amount without changing its value.
_FILLERS: Final[frozenset[str]] = frozenset(
    {"and", "only", "rupees", "rupee", "rs", "inr", "paise", "paisa"}
)

#: Suffixes that multiply a number written in digits, as in ``1.5 lakh``.
_DIGIT_SUFFIXES: Final[dict[str, int]] = {
    "k": 1_000,
    "thousand": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "million": 1_000_000,
    "billion": 1_000_000_000,
}

_WORD_RE: Final = re.compile(r"[A-Za-z]+")

#: A run of digits with optional Indian or Western grouping and decimals.
#:
#: The word-boundary guards keep lettered section numbers such as ``498A`` and
#: ``65B`` out of the figure check: they are labels, not quantities, and the same
#: label produces no token on either side of the comparison.
_NUMBER_RE: Final = re.compile(r"(?<!\w)(\d{1,3}(?:,\d{2,3})+(?:\.\d+)?|\d+(?:\.\d+)?)(?!\w)")

_SUFFIX_RE: Final = re.compile(r"\s*([A-Za-z]+)")


@dataclass(frozen=True, slots=True)
class FoundAmount:
    """An amount located in a piece of text.

    Attributes:
        value: The numeric value, exact.
        raw: The text it was read from.
        start: Inclusive start offset in the source text.
        end: Exclusive end offset in the source text.
    """

    value: Decimal
    raw: str
    start: int
    end: int


def words_to_number(phrase: str) -> Decimal | None:
    """Convert an Indian-English number phrase to a value.

    Args:
        phrase: Text such as ``"Sixty-Five Thousand"`` or ``"one crore twenty lakh"``.

    Returns:
        The value, or ``None`` when the phrase holds no number words.
    """
    tokens = _WORD_RE.findall(phrase.lower().replace("-", " "))
    total = 0
    current = 0
    seen_number_word = False

    for token in tokens:
        if token in _FILLERS:
            continue
        if token in _UNITS:
            current += _UNITS[token]
            seen_number_word = True
        elif token == _HUNDRED:
            current = max(current, 1) * 100
            seen_number_word = True
        elif token in _SCALES:
            total += max(current, 1) * _SCALES[token]
            current = 0
            seen_number_word = True
        else:
            break

    return Decimal(total + current) if seen_number_word else None


def find_word_amounts(text: str) -> list[FoundAmount]:
    """Find every amount spelled out in words.

    Args:
        text: Text to scan, typically a clause body.

    Returns:
        The amounts found, in order of appearance.
    """
    found: list[FoundAmount] = []
    matches = list(_WORD_RE.finditer(text))
    index = 0

    while index < len(matches):
        run_start = index
        has_number_word = False
        while index < len(matches):
            token = matches[index].group().lower()
            if token in _UNITS or token == _HUNDRED or token in _SCALES:
                has_number_word = True
            elif not (token in _FILLERS and has_number_word):
                break
            index += 1

        if has_number_word:
            start = matches[run_start].start()
            end = matches[index - 1].end()
            raw = text[start:end]
            value = words_to_number(raw)
            if value is not None:
                found.append(FoundAmount(value=value, raw=raw.strip(), start=start, end=end))
        else:
            index = max(index + 1, run_start + 1)

    return found


def find_digit_amounts(text: str) -> list[FoundAmount]:
    """Find every amount written in digits, applying any ``lakh``/``crore`` suffix.

    Args:
        text: Text to scan.

    Returns:
        The amounts found, in order of appearance.
    """
    source = devanagari_digits_to_ascii(text)
    found: list[FoundAmount] = []

    for match in _NUMBER_RE.finditer(source):
        try:
            value = Decimal(match.group(1).replace(",", ""))
        except InvalidOperation:  # pragma: no cover - the regex cannot produce this
            continue
        end = match.end()
        suffix = _SUFFIX_RE.match(source, end)
        if suffix and suffix.group(1).lower() in _DIGIT_SUFFIXES:
            value *= _DIGIT_SUFFIXES[suffix.group(1).lower()]
            end = suffix.end()
        found.append(
            FoundAmount(value=value, raw=source[match.start() : end], start=match.start(), end=end)
        )

    return found


def digit_values(text: str) -> frozenset[Decimal]:
    """Collect only the numbers written in digits.

    Used for the claim side of the figure check. The prompt contract requires
    explanations to write numbers as digits, so checking words there as well
    would reject correct prose: "One clause sets 30 days" opens with an ordinary
    English word, not a figure.

    Args:
        text: Text to scan.

    Returns:
        The distinct values written in digits.
    """
    return frozenset(amount.value for amount in find_digit_amounts(text))


def numeric_values(text: str) -> frozenset[Decimal]:
    """Collect every number in the text, however it is written.

    Both spellings of one amount collapse to the same value, so a statement
    saying ``65000`` matches a clause saying ``Sixty-Five Thousand``.

    Args:
        text: Text to scan.

    Returns:
        The distinct values found.
    """
    values = {amount.value for amount in find_digit_amounts(text)}
    values.update(amount.value for amount in find_word_amounts(text))
    return frozenset(values)
