"""Normalisation must be reversible: every normalised character maps back."""

import unicodedata

import pytest
from app.domain.normalize import (
    devanagari_digits_to_ascii,
    normalize,
    normalize_with_map,
    to_nfc,
)
from hypothesis import given
from hypothesis import strategies as st


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Hello   World", "hello world"),
        ("  leading and trailing  ", "leading and trailing"),
        ("line\nbreak", "line break"),
        ("“quoted”", '"quoted"'),
        ("it’s", "it's"),
        ("en–dash", "en-dash"),
        ("em—dash", "em-dash"),
        ("zero\u200bwidth", "zerowidth"),
        ("soft­hyphen", "softhyphen"),
        ("२० days", "20 days"),
        ("MiXeD CaSe", "mixed case"),
    ],
)
def test_normalize_collapses_variants(raw: str, expected: str) -> None:
    assert normalize(raw) == expected


def test_offset_map_points_at_the_source_characters() -> None:
    source = "The  deposit is ₹ 60,000 only"
    result = normalize_with_map(source)
    index = result.text.index("60,000")
    start, end = result.to_source_span(index, index + len("60,000"))
    assert source[start:end] == "60,000"


def test_offset_map_spans_a_collapsed_whitespace_run() -> None:
    source = "pay   the    deposit"
    result = normalize_with_map(source)
    start, end = result.to_source_span(0, len(result.text))
    assert source[start:end] == source


@pytest.mark.parametrize(("start", "end"), [(0, 0), (5, 2), (-1, 3), (0, 9999)])
def test_out_of_range_spans_collapse(start: int, end: int) -> None:
    assert normalize_with_map("some text").to_source_span(start, end) == (0, 0)


def test_empty_text_normalises_to_empty() -> None:
    result = normalize_with_map("")
    assert result.text == ""
    assert result.to_source_span(0, 1) == (0, 0)


def test_devanagari_digits_convert_without_touching_letters() -> None:
    assert devanagari_digits_to_ascii("२० दिन") == "20 दिन"


def test_to_nfc_is_idempotent() -> None:
    decomposed = "é"
    assert to_nfc(decomposed) == unicodedata.normalize("NFC", decomposed)
    assert to_nfc(to_nfc(decomposed)) == to_nfc(decomposed)


@given(st.text(min_size=1, max_size=120))
def test_every_normalised_character_maps_inside_the_source(raw: str) -> None:
    result = normalize_with_map(raw)
    source = to_nfc(raw)
    assert len(result.starts) == len(result.text) == len(result.ends)
    for start, end in zip(result.starts, result.ends, strict=True):
        assert 0 <= start < end <= len(source)


@given(st.text(min_size=1, max_size=120))
def test_normalised_text_has_no_runs_of_whitespace(raw: str) -> None:
    text = normalize(raw)
    assert "  " not in text
    assert text == text.strip()
