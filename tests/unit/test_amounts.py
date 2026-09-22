"""Indian number handling, and the words-versus-digits mismatch it detects."""

from decimal import Decimal

import pytest
from app.domain.amounts import (
    digit_values,
    find_digit_amounts,
    find_mismatches,
    find_word_amounts,
    numeric_values,
    words_to_number,
)


@pytest.mark.parametrize(
    ("phrase", "expected"),
    [
        ("Sixty Thousand", 60_000),
        ("Sixty-Five Thousand", 65_000),
        ("one lakh", 100_000),
        ("Two Lakhs Fifty Thousand", 250_000),
        ("one crore twenty lakh fifty thousand", 12_050_000),
        ("Rupees Eight Lakh only", 800_000),
        ("nineteen", 19),
        ("two hundred and fifty", 250),
        ("Nine Lakh Sixty Thousand", 960_000),
        ("five lac", 500_000),
    ],
)
def test_number_words_convert(phrase: str, expected: int) -> None:
    assert words_to_number(phrase) == Decimal(expected)


@pytest.mark.parametrize("phrase", ["", "the premises", "Rupees only", "  "])
def test_phrases_without_number_words_convert_to_nothing(phrase: str) -> None:
    assert words_to_number(phrase) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Rs. 60,000/-", 60_000),
        ("1,50,000", 150_000),
        ("150000", 150_000),
        ("₹1.5 lakh", 150_000),
        ("2 crore", 20_000_000),
        ("5%", 5),
        ("the deposit is 99000.", 99_000),
        ("Rs.60,000", 60_000),
    ],
)
def test_digit_amounts_are_read_with_their_multiplier(text: str, expected: int) -> None:
    assert Decimal(expected) in digit_values(text)


@pytest.mark.parametrize("text", ["section 498A", "S. 65B", "clause 7A"])
def test_lettered_section_numbers_are_not_amounts(text: str) -> None:
    assert digit_values(text) == frozenset()


def test_a_date_yields_each_of_its_parts() -> None:
    assert digit_values("on 2026-04-01") == {Decimal(2026), Decimal(4), Decimal(1)}


def test_numeric_values_unites_both_spellings() -> None:
    values = numeric_values("Rs. 60,000/- (Rupees Sixty Thousand only)")
    assert values == {Decimal(60_000)}


def test_digit_values_ignores_words() -> None:
    assert digit_values("One clause sets 30 days") == {Decimal(30)}
    assert Decimal(1) in numeric_values("One clause sets 30 days")


def test_word_amounts_report_where_they_were_found() -> None:
    found = find_word_amounts("pay Rupees Sixty Thousand only today")
    assert len(found) == 1
    assert found[0].value == Decimal(60_000)
    assert found[0].start < found[0].end


# ---------------------------------------------------------------- mismatches


def test_a_money_amount_written_two_ways_is_flagged() -> None:
    mismatches = find_mismatches("a deposit of Rs. 60,000/- (Rupees Sixty-Five Thousand only)")
    assert len(mismatches) == 1
    assert mismatches[0].digits_value == Decimal(60_000)
    assert mismatches[0].words_value == Decimal(65_000)


def test_matching_words_and_digits_are_not_flagged() -> None:
    assert find_mismatches("Rs. 18,000/- (Rupees Eighteen Thousand only)") == []


@pytest.mark.parametrize(
    "text",
    [
        "admeasuring 620 square feet, together with one covered parking space",
        "commence on 1 May 2026 and continue for a period of eleven months",
        "interest at 2% per month on the outstanding amount",
        "two witnesses signed on 15 March 2026",
    ],
)
def test_numbers_that_do_not_restate_money_are_not_flagged(text: str) -> None:
    assert find_mismatches(text) == []


def test_a_bracketed_restatement_without_a_currency_prefix_is_still_money() -> None:
    assert len(find_mismatches("a sum of 45,000 (Forty Thousand only)")) == 1


def test_amounts_far_apart_are_not_compared() -> None:
    text = "Rs. 60,000/- " + "x" * 200 + " Rupees Sixty-Five Thousand only"
    assert find_mismatches(text) == []


def test_devanagari_digits_are_read_as_numbers() -> None:
    assert Decimal(60_000) in digit_values("₹६०,०००")


def test_amounts_are_returned_in_document_order() -> None:
    amounts = find_digit_amounts("first 100 then 200 then 300")
    assert [amount.value for amount in amounts] == [Decimal(100), Decimal(200), Decimal(300)]
