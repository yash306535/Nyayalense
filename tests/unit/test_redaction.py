"""Masking must catch real identifiers and leave ordinary numbers alone."""

import pytest
from app.domain.enums import IdentifierKind
from app.domain.redaction import (
    MASKS,
    describe_masking,
    mask_identifiers,
    verhoeff_is_valid,
)


def _valid_aadhaar(prefix: str = "23456789012") -> str:
    """Build a synthetic twelve-digit value that satisfies the checksum."""
    for digit in "0123456789":
        if verhoeff_is_valid(prefix + digit):
            return prefix + digit
    raise AssertionError("no valid check digit exists for this prefix")


def test_a_valid_checksum_is_accepted_and_an_invalid_one_is_not() -> None:
    valid = _valid_aadhaar()
    assert verhoeff_is_valid(valid)
    wrong_check_digit = valid[:-1] + str((int(valid[-1]) + 1) % 10)
    assert not verhoeff_is_valid(wrong_check_digit)


@pytest.mark.parametrize("value", ["", "abcd", "12a4", "not digits"])
def test_non_digits_never_pass_the_checksum(value: str) -> None:
    assert not verhoeff_is_valid(value)


@pytest.mark.parametrize("separator", ["", " ", "-"])
def test_aadhaar_is_masked_however_it_is_grouped(separator: str) -> None:
    value = _valid_aadhaar()
    written = separator.join([value[:4], value[4:8], value[8:]])
    result = mask_identifiers(f"Aadhaar {written} on file")
    assert MASKS[IdentifierKind.AADHAAR] in result.text
    assert result.counts[IdentifierKind.AADHAAR] == 1


def test_a_twelve_digit_number_that_fails_the_checksum_is_left_alone() -> None:
    """An invoice number must stay readable, so the checksum is the gate."""
    invalid = "234567890123"
    assert not verhoeff_is_valid(invalid)
    assert invalid in mask_identifiers(f"Invoice {invalid} dated today").text


def test_a_twelve_digit_number_starting_with_one_is_not_aadhaar() -> None:
    assert "123456789012" in mask_identifiers("Reference 123456789012").text


def test_pan_is_masked() -> None:
    result = mask_identifiers("PAN ABCDE1234F is on record")
    assert MASKS[IdentifierKind.PAN] in result.text
    assert result.counts[IdentifierKind.PAN] == 1


@pytest.mark.parametrize("value", ["ABCD1234F", "ABCDE1234", "ABCDE12345", "abcde1234f"])
def test_strings_that_are_not_pan_are_left_alone(value: str) -> None:
    assert value in mask_identifiers(f"Code {value} here").text


@pytest.mark.parametrize(
    "number", ["9876543210", "+91 9876543210", "09876543210", "98765 43210", "+91-9876543210"]
)
def test_indian_mobile_numbers_are_masked(number: str) -> None:
    assert MASKS[IdentifierKind.PHONE] in mask_identifiers(f"Call {number} now").text


@pytest.mark.parametrize("number", ["1234567890", "5876543210", "12345"])
def test_numbers_that_are_not_indian_mobiles_are_left_alone(number: str) -> None:
    assert number in mask_identifiers(f"Ref {number}").text


@pytest.mark.parametrize(
    "address", ["a.b@x.co.in", "raj+tag@example.org", "first.last@sub.domain.com"]
)
def test_email_addresses_are_masked(address: str) -> None:
    assert MASKS[IdentifierKind.EMAIL] in mask_identifiers(f"Write to {address}.").text


def test_an_email_is_masked_before_its_digits_look_like_a_phone_number() -> None:
    result = mask_identifiers("Contact 9876543210@example.com for details")
    assert result.counts.get(IdentifierKind.PHONE) is None
    assert result.counts[IdentifierKind.EMAIL] == 1


def test_everything_is_counted_together() -> None:
    result = mask_identifiers(
        f"Aadhaar {_valid_aadhaar()}, PAN ABCDE1234F, phone 9876543210, mail a@b.co"
    )
    assert result.total == 4


def test_text_with_no_identifiers_is_returned_unchanged() -> None:
    text = "The licence fee is Rs. 18,000 per month."
    result = mask_identifiers(text)
    assert result.text == text
    assert result.total == 0


LABELS = {
    "aadhaar": "Aadhaar number",
    "aadhaar_plural": "Aadhaar numbers",
    "phone": "phone number",
    "phone_plural": "phone numbers",
}


def test_the_masking_sentence_reads_naturally() -> None:
    sentence = describe_masking({IdentifierKind.AADHAAR: 2, IdentifierKind.PHONE: 1}, labels=LABELS)
    assert sentence == "2 Aadhaar numbers and 1 phone number were hidden before analysis."


def test_a_single_identifier_reads_grammatically() -> None:
    sentence = describe_masking({IdentifierKind.PHONE: 1}, labels=LABELS)
    assert sentence == "1 phone number was hidden before analysis."


def test_several_of_one_kind_needs_no_conjunction() -> None:
    sentence = describe_masking({IdentifierKind.PHONE: 3}, labels=LABELS)
    assert sentence == "3 phone numbers were hidden before analysis."


def test_nothing_hidden_produces_no_sentence() -> None:
    assert describe_masking({}, labels=LABELS) == ""
