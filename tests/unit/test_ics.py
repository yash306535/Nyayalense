"""RFC 5545 output. The format has exact rules that a naive writer gets wrong."""

from datetime import UTC, date, datetime

import pytest
from app.domain.ics import CRLF, MAX_OCTETS, build_calendar, escape_text, fold

NOW = datetime(2026, 1, 1, 12, 30, 45, tzinfo=UTC)


def calendar(events: list[tuple[str, date, str]] | None = None) -> str:
    return build_calendar(
        events or [("Rent due", date(2026, 5, 5), "From clause 3.1")],
        uid_namespace="doc1",
        now=NOW,
    )


def lines(text: str) -> list[str]:
    return text.split(CRLF)


def test_every_line_ends_with_crlf() -> None:
    output = calendar()
    assert output.count("\n") == output.count("\r\n")
    assert output.endswith(CRLF)


def test_the_envelope_is_complete() -> None:
    content = lines(calendar())
    assert content[0] == "BEGIN:VCALENDAR"
    assert "VERSION:2.0" in content
    assert any(line.startswith("PRODID:") for line in content)
    assert "END:VCALENDAR" in content


def test_an_event_carries_a_uid_and_a_timestamp() -> None:
    content = lines(calendar())
    assert "UID:doc1-1@nyayalens.invalid" in content
    assert "DTSTAMP:20260101T123045Z" in content
    assert "DTSTART;VALUE=DATE:20260505" in content


def test_events_are_all_day_because_a_deadline_is_a_day() -> None:
    assert "DTSTART;VALUE=DATE:" in calendar()
    assert "DTSTART:2026" not in calendar()


def test_uids_are_stable_so_reimporting_updates_rather_than_duplicates() -> None:
    assert calendar() == calendar()


def test_several_events_get_distinct_uids() -> None:
    output = calendar([("One", date(2026, 5, 5), ""), ("Two", date(2026, 6, 5), "")])
    assert "UID:doc1-1@nyayalens.invalid" in output
    assert "UID:doc1-2@nyayalens.invalid" in output


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("a;b", r"a\;b"),
        ("a,b", r"a\,b"),
        ("a\nb", r"a\nb"),
        ("a\\b", r"a\\b"),
        ("plain", "plain"),
    ],
)
def test_text_values_are_escaped(raw: str, expected: str) -> None:
    assert escape_text(raw) == expected


def test_a_carriage_return_is_dropped_rather_than_escaped() -> None:
    assert escape_text("a\r\nb") == r"a\nb"


def test_a_summary_with_separators_does_not_break_the_file() -> None:
    output = calendar([("Pay rent; deposit, too", date(2026, 5, 5), "")])
    summary = next(line for line in lines(output) if line.startswith("SUMMARY:"))
    assert summary == r"SUMMARY:Pay rent\; deposit\, too"


# ---------------------------------------------------------------- folding


def test_a_short_line_is_not_folded() -> None:
    assert fold("SHORT:value") == "SHORT:value"


def test_a_long_line_folds_at_the_octet_limit() -> None:
    folded = fold("SUMMARY:" + "a" * 200)
    parts = folded.split(CRLF)
    assert len(parts) > 1
    assert all(len(part.encode()) <= MAX_OCTETS for part in parts)
    assert all(part.startswith(" ") for part in parts[1:])


def test_folding_counts_octets_not_characters() -> None:
    """Devanagari is three octets per character, so a naive fold overruns."""
    folded = fold("SUMMARY:" + "देय" * 40)
    assert all(len(part.encode()) <= MAX_OCTETS for part in folded.split(CRLF))


def test_folding_never_splits_a_character() -> None:
    folded = fold("SUMMARY:" + "मराठी" * 30)
    for part in folded.split(CRLF):
        part.encode().decode()  # would raise if a character were cut in half


def test_a_devanagari_summary_survives_a_whole_file() -> None:
    output = calendar([("भाडे देय तारीख " * 8, date(2026, 5, 5), "कलम ३.१ नुसार")])
    assert all(len(line.encode()) <= MAX_OCTETS for line in lines(output))


def test_unfolding_restores_the_original_value() -> None:
    original = "SUMMARY:" + "x" * 300
    restored = fold(original).replace(f"{CRLF} ", "")
    assert restored == original
