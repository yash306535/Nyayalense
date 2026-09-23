"""The slot lock.

A model may be asked to word a sentence better. It may not be trusted with a
fact. So its wording refers to facts only through ``[[slot]]`` tokens, and this
module rejects any wording that names an unknown slot, drops a required one,
runs too long, or writes a figure, a date, an address or a number of its own
anywhere outside a slot. Code then fills the slots from the confirmed facts.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

SLOT_RE: Final = re.compile(r"\[\[([a-z][a-z0-9_]*)\]\]")


class Violation(StrEnum):
    """Why suggested wording was rejected."""

    UNKNOWN_SLOT = "unknown_slot"
    MISSING_REQUIRED_SLOT = "missing_required_slot"
    TOO_LONG = "too_long"
    DIGIT_OUTSIDE_SLOT = "digit_outside_slot"
    CONTACT_OUTSIDE_SLOT = "contact_outside_slot"
    EMPTY = "empty"


_DIGIT_RE: Final = re.compile(r"\d")
_EMAIL_RE: Final = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
_PHONE_RE: Final = re.compile(r"(?<!\d)[6-9]\d{9}(?!\d)")

#: Month names would let a model write a date without a digit in sight.
_MONTHS: Final = (
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
)  # fmt: skip


@dataclass(frozen=True, slots=True)
class SlotCheck:
    """The outcome of checking one piece of suggested wording."""

    ok: bool
    violation: Violation | None = None
    detail: str = ""
    slots: tuple[str, ...] = ()


def find_slots(text: str) -> list[str]:
    """List the slot tokens a piece of text uses, in order.

    Args:
        text: The wording to inspect.

    Returns:
        The slot names, which may repeat.
    """
    return SLOT_RE.findall(text)


def strip_slots(text: str) -> str:
    """Remove every slot token, leaving only the model's own words.

    Args:
        text: The wording.

    Returns:
        The text with all ``[[slot]]`` tokens removed.
    """
    return SLOT_RE.sub(" ", text)


def check(text: str, *, allowed: set[str], required: set[str], max_words: int) -> SlotCheck:
    """Check suggested wording against the slot contract.

    The rules are applied in order and the first failure is reported, so the
    message names the thing the model actually got wrong.

    Args:
        text: The wording the model returned.
        allowed: Slot names the template defines.
        required: Slot names the wording must contain.
        max_words: Longest acceptable wording.

    Returns:
        The outcome, naming the first rule that was broken.
    """
    stripped = text.strip()
    for broken, violation, detail in _rules(
        stripped, allowed=allowed, required=required, max_words=max_words
    ):
        if broken:
            return SlotCheck(False, violation, detail)
    return SlotCheck(True, slots=tuple(dict.fromkeys(find_slots(stripped))))


def _rules(
    text: str, *, allowed: set[str], required: set[str], max_words: int
) -> tuple[tuple[bool, Violation, str], ...]:
    """Build the ordered contract, each entry a condition and what it means.

    Args:
        text: The stripped wording.
        allowed: Slot names the template defines.
        required: Slot names the wording must contain.
        max_words: Longest acceptable wording.

    Returns:
        Each rule as ``(broken, violation, detail)``, most fundamental first.
    """
    used = set(find_slots(text))
    outside = strip_slots(text)

    return (
        (not text, Violation.EMPTY, "The suggestion was empty."),
        (
            len(text.split()) > max_words,
            Violation.TOO_LONG,
            f"Longer than {max_words} words.",
        ),
        (
            bool(used - allowed),
            Violation.UNKNOWN_SLOT,
            f"Unknown slot: {', '.join(sorted(used - allowed))}",
        ),
        (
            bool(required - used),
            Violation.MISSING_REQUIRED_SLOT,
            f"Missing required slot: {', '.join(sorted(required - used))}",
        ),
        (
            bool(_DIGIT_RE.search(outside)),
            Violation.DIGIT_OUTSIDE_SLOT,
            "A digit appears outside a slot.",
        ),
        (
            any(month in outside.casefold() for month in _MONTHS),
            Violation.DIGIT_OUTSIDE_SLOT,
            "A date appears outside a slot.",
        ),
        (
            bool(_EMAIL_RE.search(outside) or _PHONE_RE.search(outside)),
            Violation.CONTACT_OUTSIDE_SLOT,
            "A contact detail appears outside a slot.",
        ),
    )


def fill(text: str, values: dict[str, str]) -> str:
    """Replace every slot token with the confirmed fact it names.

    This is the step that puts facts into the letter, and it is ordinary string
    substitution, so the model never types a fact even when it suggested the
    sentence around it.

    Args:
        text: Wording that has passed :func:`check`.
        values: The user's confirmed facts.

    Returns:
        The wording with slots replaced. An unfilled slot becomes an empty
        string rather than leaving a token in a letter someone will send.
    """
    return SLOT_RE.sub(lambda match: values.get(match.group(1), ""), text).strip()
