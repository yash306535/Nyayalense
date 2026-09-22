"""The slot lock and the fact audit: the two gates on a generated letter."""

from decimal import Decimal

import pytest
from app.domain.document_model import DocumentModel, bullets, heading, paragraph, table
from app.domain.drafting.fact_audit import audit
from app.domain.drafting.slots import Violation, check, fill, find_slots, strip_slots

ALLOWED = {"deposit_amount", "move_out_date", "landlord_name"}


def run(text: str, *, required: set[str] | None = None, max_words: int = 60):
    return check(text, allowed=ALLOWED, required=required or set(), max_words=max_words)


# ---------------------------------------------------------------- slot lock


def test_wording_that_keeps_to_slots_is_accepted() -> None:
    outcome = run("I request the refund of [[deposit_amount]] paid before [[move_out_date]].")
    assert outcome.ok
    assert set(outcome.slots) == {"deposit_amount", "move_out_date"}


def test_a_figure_outside_a_slot_is_rejected() -> None:
    """The whole point: a model must never type a number into a letter."""
    outcome = run("I request the refund of Rs. 60,000.")
    assert not outcome.ok
    assert outcome.violation is Violation.DIGIT_OUTSIDE_SLOT


def test_a_month_name_is_treated_as_a_date() -> None:
    outcome = run("I moved out in March.")
    assert outcome.violation is Violation.DIGIT_OUTSIDE_SLOT


def test_an_email_outside_a_slot_is_rejected() -> None:
    assert run("Write to me at raj@example.com.").violation is Violation.CONTACT_OUTSIDE_SLOT


def test_a_phone_number_outside_a_slot_is_rejected() -> None:
    """Caught by the digit rule first, which is the same refusal either way."""
    outcome = run("Call me on 9876543210 any time.")
    assert not outcome.ok
    assert outcome.violation in {Violation.DIGIT_OUTSIDE_SLOT, Violation.CONTACT_OUTSIDE_SLOT}


def test_an_unknown_slot_is_rejected() -> None:
    outcome = run("I refer to [[bank_account]].")
    assert outcome.violation is Violation.UNKNOWN_SLOT
    assert "bank_account" in outcome.detail


def test_dropping_a_required_slot_is_rejected() -> None:
    outcome = run("Please refund the deposit.", required={"deposit_amount"})
    assert outcome.violation is Violation.MISSING_REQUIRED_SLOT


def test_over_long_wording_is_rejected() -> None:
    assert run(" ".join(["word"] * 80), max_words=60).violation is Violation.TOO_LONG


@pytest.mark.parametrize("text", ["", "   ", "\n"])
def test_empty_wording_is_rejected(text: str) -> None:
    assert run(text).violation is Violation.EMPTY


def test_the_first_broken_rule_is_the_one_reported() -> None:
    outcome = run("[[nope]] and 60000", required={"deposit_amount"})
    assert outcome.violation is Violation.UNKNOWN_SLOT


def test_slots_are_found_in_order_and_repeats_kept() -> None:
    assert find_slots("[[a]] then [[b]] then [[a]]") == ["a", "b", "a"]


def test_stripping_slots_leaves_only_the_model_own_words() -> None:
    assert "deposit_amount" not in strip_slots("Refund [[deposit_amount]] now.")


def test_filling_substitutes_confirmed_facts() -> None:
    filled = fill(
        "Refund [[deposit_amount]] by [[move_out_date]].",
        {"deposit_amount": "60,000", "move_out_date": "2027-03-31"},
    )
    assert filled == "Refund 60,000 by 2027-03-31."


def test_an_unfilled_slot_becomes_nothing_rather_than_a_visible_token() -> None:
    assert "[[" not in fill("Refund [[deposit_amount]].", {})


# ---------------------------------------------------------------- fact audit


def model(*texts: str) -> DocumentModel:
    return DocumentModel(title="t", blocks=[paragraph(text) for text in texts])


def test_a_document_whose_figures_are_all_confirmed_passes() -> None:
    result = audit(model("The deposit is 60,000."), confirmed={"deposit_amount": "60,000"})
    assert result.ok
    assert result.describe() == ""


def test_a_figure_that_is_not_a_confirmed_fact_fails_the_audit() -> None:
    result = audit(model("The deposit is 99,000."), confirmed={"deposit_amount": "60,000"})
    assert not result.ok
    assert Decimal(99_000) in result.unexplained
    assert "99000" in result.describe()


def test_a_figure_from_the_template_itself_is_allowed() -> None:
    result = audit(
        model("Reply within 15 days."),
        confirmed={},
        template_constants="Reply within 15 days of this letter.",
    )
    assert result.ok


def test_figures_in_lists_and_tables_are_audited_too() -> None:
    document = DocumentModel(
        title="t",
        blocks=[
            heading("Letter"),
            bullets(["An amount of 12345"]),
            table([["Item", "Amount"], ["Deposit", "67890"]]),
        ],
    )
    result = audit(document, confirmed={})
    assert not result.ok
    assert {Decimal(12345), Decimal(67890)} <= set(result.unexplained)


def test_a_document_with_no_figures_passes_trivially() -> None:
    assert audit(model("Dear Sir, I write about the premises."), confirmed={}).ok


def test_a_date_counts_as_confirmed_when_the_user_entered_it() -> None:
    result = audit(model("I moved out on 2027-03-31."), confirmed={"move_out_date": "2027-03-31"})
    assert result.ok
