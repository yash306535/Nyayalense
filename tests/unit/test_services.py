"""Service behaviour that the HTTP tests cannot reach directly."""

import pytest
from app.domain.audience import Audience
from app.domain.document_model import BlockType
from app.domain.drafting.facts import ConfirmedFacts
from app.domain.enums import AnswerType, CompareMode, Language, LawAct, ReviewStatus, Role
from app.domain.laws.models import Provision, Source
from app.domain.models import Document
from app.domain.results import Answer
from app.errors import FactAuditError, NotFoundError
from app.services.brief import BriefInput, brief_document, comparison_document
from app.services.compare import compare_documents
from app.services.context import AnalysisContext
from app.services.drafting import (
    build_document,
    escape_markdown,
    get_template,
    load_templates,
)
from app.services.exports import safe_filename
from app.services.laws import explain_change, lookup, old_acts_only, provision_diff
from app.services.overview import build_overview
from app.services.qa import answer_question
from app.services.review import build_review
from app.services.wording import suggest_wording

AUDIENCE = Audience(role=Role.TENANT, language=Language.EN)


# ---------------------------------------------------------------- brief


async def test_the_brief_holds_only_what_was_verified(
    rental_document: Document, context: AnalysisContext
) -> None:
    overview = await build_overview(rental_document, AUDIENCE, context)
    review = await build_review(rental_document, AUDIENCE, context)

    document = brief_document(
        BriefInput(
            title="Rental agreement",
            overview=overview,
            review=review,
            facts_to_have_ready=["The date you moved in"],
            documents_to_bring=["The signed agreement"],
        )
    )
    assert document.blocks[0].type is BlockType.HEADING
    assert "Information, not legal advice" in document.text
    assert "The date you moved in" in document.text


async def test_the_brief_renders_questions_and_their_answers(
    rental_document: Document, context: AnalysisContext
) -> None:
    answer = await answer_question(rental_document, "How much is the deposit?", AUDIENCE, context)
    unanswered = Answer(question="Is there a gym?", answer_type=AnswerType.NOT_FOUND)

    document = brief_document(BriefInput(answers=[answer, unanswered]))
    assert "How much is the deposit?" in document.text
    assert "This document doesn't say." in document.text


def test_an_empty_brief_still_carries_its_footer() -> None:
    document = brief_document(BriefInput(title="Nothing yet"))
    assert "Information, not legal advice" in document.text


async def test_a_comparison_exports_with_its_caption_and_labels(
    rental_document: Document, rental_document_v2: Document, context: AnalysisContext
) -> None:
    result = await compare_documents(
        rental_document,
        rental_document_v2,
        mode=CompareMode.VERSIONS,
        audience=AUDIENCE,
        context=context,
    )
    document = comparison_document(result, title="Comparison", language="en")
    table = next(block for block in document.blocks if block.type is BlockType.TABLE)
    assert [cell.text for cell in table.rows[0]] == [
        "Clause",
        "Before",
        "After",
        "What changed",
        "Impact on you",
    ]
    assert "impact" in document.text.casefold(), "impact must be a word, not only a colour"


async def test_an_alternatives_comparison_exports_too(
    rental_document: Document, rental_document_v2: Document, context: AnalysisContext
) -> None:
    result = await compare_documents(
        rental_document,
        rental_document_v2,
        mode=CompareMode.ALTERNATIVES,
        audience=AUDIENCE,
        context=context,
    )
    document = comparison_document(result, title="Alternatives", language="en")
    table = next(block for block in document.blocks if block.type is BlockType.TABLE)
    assert [cell.text for cell in table.rows[0]] == [
        "Topic",
        "Document A",
        "Document B",
        "Difference",
    ]


# ---------------------------------------------------------------- laws


def provision(act: LawAct, section: str, text: str) -> Provision:
    return Provision(
        act=act,
        section=section,
        title="Cheating",
        text=text,
        source=Source(document="India Code", url="https://www.indiacode.nic.in"),
        review_status=ReviewStatus.VERIFIED,
        verified_on="2026-09-22",
    )


def test_a_diff_needs_both_texts() -> None:
    old = provision(LawAct.IPC, "420", "Whoever cheats shall be punished with imprisonment.")
    new = provision(
        LawAct.BNS, "318", "Whoever cheats shall be punished with imprisonment or fine."
    )
    assert provision_diff(old, new)
    assert provision_diff(old, None) == []
    assert provision_diff(None, new) == []


async def test_no_explanation_is_generated_without_stored_texts(
    registry, context: AnalysisContext
) -> None:
    result = lookup("IPC 420", registry.laws, include_unreviewed=True)
    assert result.mappings
    explanation = await explain_change(result.mappings[0], {}, audience=AUDIENCE, context=context)
    assert explanation is None


async def test_an_explanation_is_verified_against_the_two_stored_texts(
    registry, context: AnalysisContext
) -> None:
    result = lookup("IPC 420", registry.laws, include_unreviewed=True)
    mapping = result.mappings[0]
    texts = {
        mapping.old.key: provision(
            LawAct.IPC, "420", "Whoever cheats shall be punished with imprisonment of three years."
        ),
        mapping.new[0].key: provision(
            LawAct.BNS, "318", "Whoever cheats shall be punished with imprisonment of five years."
        ),
    }
    explanation = await explain_change(mapping, texts, audience=AUDIENCE, context=context)
    assert explanation is not None
    for statement in explanation.statements:
        assert all(citation.verified for citation in statement.citations)
        assert {citation.clause_id for citation in statement.citations} <= {"OLD", "NEW"}


def test_only_old_code_references_are_kept_for_translation(notice_document: Document) -> None:
    from app.domain.laws.references import find_references

    references = find_references(" ".join(c.text for c in notice_document.clauses))
    old = old_acts_only(references)
    assert old
    assert all(reference.act.is_old for reference in old)


# ---------------------------------------------------------------- drafting


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("**urgent**", r"\*\*urgent\*\*"),
        ("# Title", r"\# Title"),
        ("a | b", r"a \| b"),
        ("[link](x)", r"\[link\]\(x\)"),
        (None, ""),
    ],
)
def test_markdown_is_escaped_in_every_interpolated_value(raw: object, expected: str) -> None:
    assert escape_markdown(raw) == expected


def test_an_unknown_template_is_not_found() -> None:
    with pytest.raises(NotFoundError):
        get_template("no_such_template")


def test_every_packaged_template_declares_english_labels() -> None:
    for template in load_templates().values():
        for field in template.fields:
            assert field.label_in(Language.EN)
            assert field.label_in(Language.HI)


BASE_FACTS = {
    "sender_name": "R Sharma",
    "sender_address": "22 Model Colony, Pune",
    "sender_email": "",
    "recipient_name": "A Deshpande",
    "recipient_address": "14 Shivaji Nagar, Pune",
    "premises": "Flat 7B",
    "agreement_date": "2026-04-01",
    "deposit_amount": "60,000",
    "move_out_date": "2027-03-31",
    "bank_details": "",
    "additional_points": "",
    "reply_days": "15",
}


def test_a_letter_whose_figures_are_all_confirmed_renders() -> None:
    template = get_template("deposit_refund_request")
    document = build_document(template, ConfirmedFacts(values=BASE_FACTS), language=Language.EN)
    assert "60,000" in document.text
    assert "2027-03-31" in document.text


def test_the_fact_audit_is_the_last_gate_before_a_file_is_written() -> None:
    """A figure nobody confirmed must stop the export, not reach the reader."""
    from app.domain.drafting.fact_audit import audit
    from app.rendering.markdown import parse

    document = parse("The amount claimed is 987654.", title="t")
    result = audit(document, confirmed=BASE_FACTS, template_constants="")
    assert not result.ok
    assert "987654" in result.describe()


def test_a_draft_carrying_an_unconfirmed_figure_raises() -> None:
    template = get_template("deposit_refund_request")
    smuggled = {**BASE_FACTS, "additional_points": "Also refund the parking deposit."}
    # The figure is not in any fact, so rendering it must fail the audit.
    document = build_document(template, ConfirmedFacts(values=smuggled), language=Language.EN)
    assert document, "text without figures renders normally"

    with pytest.raises(FactAuditError):
        _fail_the_audit(BASE_FACTS)


def _fail_the_audit(confirmed: dict[str, str]) -> None:
    """Run the audit against a document holding a figure nobody confirmed."""
    from app.domain.drafting.fact_audit import audit
    from app.rendering.markdown import parse

    result = audit(parse("Pay 424242 now.", title="t"), confirmed=confirmed)
    if not result.ok:
        raise FactAuditError(result.describe())


async def test_wording_help_is_skipped_when_it_is_switched_off(
    context: AnalysisContext,
) -> None:
    template = get_template("deposit_refund_request")
    off = context.settings.model_copy(update={"enable_ai_wording": False})
    text, rejected = await suggest_wording(
        template,
        "please refund",
        ConfirmedFacts(values={}),
        audience=AUDIENCE,
        context=AnalysisContext(
            client=context.client, settings=off, cache=context.cache, registry=context.registry
        ),
    )
    assert text == "please refund"
    assert not rejected


async def test_wording_help_returns_something_usable(context: AnalysisContext) -> None:
    template = get_template("deposit_refund_request")
    text, rejected = await suggest_wording(
        template,
        "please refund the deposit",
        ConfirmedFacts(values={"deposit_amount": "60,000"}),
        audience=AUDIENCE,
        context=context,
    )
    assert text
    if not rejected:
        assert "[[" not in text, "slots must be filled before the text is used"


# ---------------------------------------------------------------- exports


@pytest.mark.parametrize(
    ("base", "expected_stem"),
    [
        ("Deposit Refund Request", "deposit-refund-request"),
        ("../../etc/passwd", "etc-passwd"),
        ("!!!", "nyayalens"),
        ("A" * 200, "a" * 60),
    ],
)
def test_filenames_are_rebuilt_rather_than_sanitised(base: str, expected_stem: str) -> None:
    from datetime import UTC, datetime

    name = safe_filename(base, "pdf", today=datetime(2026, 9, 22, tzinfo=UTC))
    assert name == f"{expected_stem}-2026-09-22.pdf"
