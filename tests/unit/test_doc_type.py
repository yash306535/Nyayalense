"""Guessing the document type from keywords, before any model is involved."""

import pytest
from app.domain.doc_type import CONFIDENT_SCORE, default_roles, guess_doc_type
from app.domain.enums import DocType, Role
from tests.conftest import sample_text


@pytest.mark.parametrize(
    ("sample", "expected"),
    [
        ("leave-licence-v1", DocType.RENTAL_LEAVE_LICENCE),
        ("leave-licence-v2", DocType.RENTAL_LEAVE_LICENCE),
        ("offer-letter-bond", DocType.EMPLOYMENT_OFFER),
        ("legal-notice-old-sections", DocType.LEGAL_NOTICE),
    ],
)
def test_each_sample_is_typed_correctly(sample: str, expected: DocType) -> None:
    guess = guess_doc_type(sample_text(sample))
    assert guess.doc_type is expected
    assert guess.is_confident


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            "This loan agreement between the borrower and the lender sets the EMI and rate of interest.",
            DocType.LOAN_AGREEMENT,
        ),
        (
            "This insurance policy states the sum insured, the premium and the waiting period for the policyholder.",
            DocType.INSURANCE_POLICY,
        ),
        (
            "These terms of service and privacy policy govern your user account on the platform.",
            DocType.TERMS_OF_SERVICE,
        ),
        (
            "This non-disclosure agreement binds the disclosing party and the receiving party over confidential information.",
            DocType.NDA,
        ),
    ],
)
def test_the_other_types_are_recognised(text: str, expected: DocType) -> None:
    assert guess_doc_type(text).doc_type is expected


def test_text_with_no_signal_falls_back_without_confidence() -> None:
    guess = guess_doc_type("Hello. This is a letter about nothing in particular.")
    assert guess.doc_type is DocType.GENERAL_CONTRACT
    assert guess.confidence == 0.0
    assert not guess.is_confident


def test_a_weak_signal_is_not_treated_as_confident() -> None:
    guess = guess_doc_type("This agreement is made today.")
    assert not guess.is_confident
    assert guess.scores[guess.doc_type] < CONFIDENT_SCORE


def test_confidence_stays_within_range() -> None:
    for sample in ("leave-licence-v1", "offer-letter-bond"):
        assert 0.0 <= guess_doc_type(sample_text(sample)).confidence <= 1.0


def test_every_type_is_scored() -> None:
    assert set(guess_doc_type("anything").scores) == set(DocType)


@pytest.mark.parametrize(
    ("doc_type", "first_role"),
    [
        (DocType.RENTAL_LEAVE_LICENCE, Role.TENANT),
        (DocType.EMPLOYMENT_OFFER, Role.EMPLOYEE),
        (DocType.LOAN_AGREEMENT, Role.BORROWER),
        (DocType.LEGAL_NOTICE, Role.NOTICE_RECIPIENT),
    ],
)
def test_the_reader_role_is_offered_first(doc_type: DocType, first_role: Role) -> None:
    assert default_roles(doc_type)[0] is first_role


def test_every_type_offers_at_least_one_role() -> None:
    for doc_type in DocType:
        assert default_roles(doc_type)


def test_marathi_rental_wording_is_recognised() -> None:
    assert guess_doc_type("हा भाडेकरार मालक आणि भाडेकरू यांच्यात झाला आहे.").doc_type is (
        DocType.RENTAL_LEAVE_LICENCE
    )
