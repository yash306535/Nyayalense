"""Detecting an amount a document writes two different ways.

A contract normally writes money twice, once in digits and once in words. When
the two disagree it is a real defect, and finding it needs no model at all.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Final

from app.domain.amounts import FoundAmount, find_digit_amounts, find_word_amounts


@dataclass(frozen=True, slots=True)
class Mismatch:
    """An amount in words that disagrees with the amount in digits beside it."""

    in_words: str
    in_digits: str
    words_value: Decimal
    digits_value: Decimal


#: How far before a spelled-out amount to look for the digits it restates.
_NEIGHBOUR_WINDOW: Final = 80

#: Below this, a restated number is a count ("two years"), not money worth flagging.
_MISMATCH_FLOOR: Final = 100

#: Words that mark a spelled-out figure as money rather than an ordinary count.
_MONEY_WORDS: Final[tuple[str, ...]] = ("rupees", "rupee", "\u0930\u0941\u092a\u092f\u0947", "only")

#: Currency markers that mark digits as money.
_CURRENCY_MARKERS: Final[tuple[str, ...]] = ("rs", "\u20b9", "inr", "rupees", "\u0930\u0941.")

#: How far before the digits to look for a currency marker.
_CURRENCY_WINDOW: Final = 12


def find_mismatches(text: str) -> list[Mismatch]:
    """Find amounts whose words and digits disagree.

    A contract normally writes an amount twice, as in
    ``Rs. 60,000/- (Rupees Sixty Thousand only)``. Each spelled-out amount is
    compared with the nearest digits just before it.

    Args:
        text: Text to scan, typically one clause.

    Returns:
        One entry per disagreement found.
    """
    digits = find_digit_amounts(text)
    mismatches: list[Mismatch] = []

    for words in find_word_amounts(text):
        neighbour = _nearest_preceding(digits, words.start)
        if neighbour is None or neighbour.value == words.value:
            continue
        if max(neighbour.value, words.value) < _MISMATCH_FLOOR:
            continue
        if not _restates_money(text, words, neighbour):
            continue
        mismatches.append(
            Mismatch(
                in_words=words.raw,
                in_digits=neighbour.raw,
                words_value=words.value,
                digits_value=neighbour.value,
            )
        )

    return mismatches


def _restates_money(text: str, words: FoundAmount, digits: FoundAmount) -> bool:
    """Decide whether a spelled-out figure restates the money beside it.

    ``620 square feet ... one covered parking space`` puts a number and a word
    close together without one restating the other. Indian drafting writes money
    twice in a fixed shape - ``Rs. 60,000/- (Rupees Sixty Thousand only)`` - so
    both halves must carry a money marker before a difference means anything.

    Args:
        text: The clause being scanned.
        words: The amount written in words.
        digits: The nearest amount written in digits before it.

    Returns:
        True when the two really are two spellings of one sum.
    """
    spelled = words.raw.casefold()
    if not any(marker in spelled for marker in _MONEY_WORDS):
        return False
    before_digits = text[max(0, digits.start - _CURRENCY_WINDOW) : digits.start].casefold()
    if any(marker in before_digits for marker in _CURRENCY_MARKERS):
        return True
    # "(Rupees Sixty Thousand only)" straight after the digits is money too.
    between = text[digits.end : words.start]
    return between.strip().startswith("(")


def _nearest_preceding(amounts: list[FoundAmount], position: int) -> FoundAmount | None:
    """Return the digit amount closest before ``position`` within the window."""
    candidates = [
        amount
        for amount in amounts
        if amount.end <= position and position - amount.end <= _NEIGHBOUR_WINDOW
    ]
    return max(candidates, key=lambda amount: amount.end) if candidates else None
