"""Write RFC 5545 calendar files.

A deadline the user never sees is the same as no deadline, so absolute dates
become a calendar file. The format has exact rules about line endings, escaping
and folding that a naive f-string gets wrong, so this module implements them and
the tests check them.
"""

from datetime import UTC, date, datetime
from typing import Final

from app.constants import APP_NAME

#: RFC 5545 section 3.1: content lines end with CRLF.
CRLF: Final = "\r\n"

#: RFC 5545 section 3.1: no line may exceed 75 octets, excluding the CRLF.
MAX_OCTETS: Final = 75

#: Characters that must be escaped inside a TEXT value, in replacement order.
_ESCAPES: Final[tuple[tuple[str, str], ...]] = (
    ("\\", r"\\"),
    (";", r"\;"),
    (",", r"\,"),
    ("\n", r"\n"),
)

PRODID: Final = f"-//{APP_NAME}//Key dates//EN"


def escape_text(value: str) -> str:
    """Escape a TEXT value for RFC 5545.

    Args:
        value: Raw text, such as an event summary.

    Returns:
        The value with backslashes, semicolons, commas and newlines escaped.
    """
    for character, replacement in _ESCAPES:
        value = value.replace(character, replacement)
    return value.replace("\r", "")


def fold(line: str) -> str:
    """Fold one content line to the 75-octet limit.

    Folding counts octets, not characters, so a Devanagari summary folds
    correctly instead of producing over-long lines.

    Args:
        line: A complete content line, without a line ending.

    Returns:
        The line, split across continuations joined by CRLF and a space.
    """
    encoded = line.encode()
    if len(encoded) <= MAX_OCTETS:
        return line

    pieces: list[str] = []
    budget = MAX_OCTETS
    current = bytearray()
    for character in line:
        chunk = character.encode()
        if len(current) + len(chunk) > budget:
            pieces.append(current.decode())
            current = bytearray()
            budget = MAX_OCTETS - 1  # continuation lines start with a space
        current += chunk
    pieces.append(current.decode())
    return (CRLF + " ").join(pieces)


def _stamp(moment: datetime) -> str:
    """Format a UTC timestamp as required by DTSTAMP."""
    return moment.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def _all_day(day: date) -> str:
    """Format a date as a DATE value."""
    return day.strftime("%Y%m%d")


def build_calendar(
    events: list[tuple[str, date, str]], *, uid_namespace: str, now: datetime | None = None
) -> str:
    """Build a complete iCalendar document.

    Events are all-day, because a contractual deadline is a day rather than a
    moment and a timed event would imply a precision the document does not have.

    Args:
        events: ``(summary, date, description)`` for each event.
        uid_namespace: Stable string, normally the document id, so re-importing
            the same file updates events instead of duplicating them.
        now: Timestamp for DTSTAMP. Defaults to the current time.

    Returns:
        The calendar as text with CRLF line endings.
    """
    stamp = _stamp(now or datetime.now(UTC))
    lines: list[str] = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
    ]

    for index, (summary, day, description) in enumerate(events, start=1):
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{uid_namespace}-{index}@nyayalens.invalid",
                f"DTSTAMP:{stamp}",
                f"DTSTART;VALUE=DATE:{_all_day(day)}",
                f"SUMMARY:{escape_text(summary)}",
                f"DESCRIPTION:{escape_text(description)}",
                "TRANSP:TRANSPARENT",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")
    return CRLF.join(fold(line) for line in lines) + CRLF
