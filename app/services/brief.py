"""Assembling the lawyer brief and the comparison tables as document models.

Everything here is a pure function of results that already passed verification,
so an export can only contain what the user was shown.
"""

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Final, Protocol

from app.domain.document_model import (
    Block,
    BlockType,
    DocumentModel,
    bullets,
    heading,
    paragraph,
    quote,
    table,
)
from app.domain.enums import CompareMode
from app.domain.results import CompareResult, Overview, Review

FOOTER: Final = "Prepared with NyayaLens. Information, not legal advice."


class StatementLike(Protocol):
    """The part of a statement the brief renders."""

    @property
    def text(self) -> str:
        """The statement's text."""


class AnswerLike(Protocol):
    """The part of an answer the brief renders.

    A Protocol rather than a concrete type, so the API layer can hand over its
    own request model without the brief depending on the HTTP layer.
    """

    @property
    def question(self) -> str:
        """The question that was asked."""

    @property
    def statements(self) -> Sequence[StatementLike]:
        """The verified statements that answered it."""


@dataclass(frozen=True, slots=True)
class BriefInput:
    """Everything the brief is assembled from, all of it already verified."""

    title: str = ""
    overview: Overview | None = None
    review: Review | None = None
    answers: Sequence[AnswerLike] = field(default_factory=tuple)
    language: str = "en"
    facts_to_have_ready: list[str] = field(default_factory=list)
    documents_to_bring: list[str] = field(default_factory=list)


def brief_document(source: BriefInput) -> DocumentModel:
    """Build the brief as a document model.

    Args:
        source: The verified results to assemble.

    Returns:
        The document model, ready for any renderer.
    """
    blocks: list[Block] = [heading("Brief for a lawyer or legal-aid clinic", 1)]
    if source.title:
        blocks.append(paragraph(source.title))

    blocks.extend(_overview_blocks(source.overview))
    blocks.extend(_review_blocks(source.review))
    blocks.extend(_answer_blocks(source.answers))

    if source.facts_to_have_ready:
        blocks.extend([heading("Facts to have ready", 2), bullets(source.facts_to_have_ready)])
    if source.documents_to_bring:
        blocks.extend([heading("Documents to bring", 2), bullets(source.documents_to_bring)])

    blocks.extend([Block(type=BlockType.RULE), paragraph(FOOTER)])
    return DocumentModel(title="Brief for a lawyer", language=source.language, blocks=blocks)


def _overview_blocks(overview: Overview | None) -> list[Block]:
    """Render the summary, parties and key terms."""
    if overview is None:
        return []
    blocks: list[Block] = [heading("The document", 2)]
    blocks.extend(paragraph(statement.text) for statement in overview.summary)

    if overview.parties:
        blocks.append(
            bullets(
                [
                    f"{party.name}{f' — {party.described_as}' if party.described_as else ''}"
                    for party in overview.parties
                ]
            )
        )
    if overview.key_terms:
        blocks.extend(
            [
                heading("Key terms", 3),
                table(
                    [["Term", "What the document says"]]
                    + [
                        [term.label, term.value or "Not specified in this document."]
                        for term in overview.key_terms
                    ]
                ),
            ]
        )
    return blocks


def _review_blocks(review: Review | None) -> list[Block]:
    """Render the risks, missing protections and contradictions."""
    if review is None:
        return []
    blocks: list[Block] = []

    if review.risks:
        blocks.append(heading("Main points to raise", 2))
        for risk in review.risks:
            blocks.append(paragraph(f"{risk.title} ({risk.severity.value} impact)"))
            blocks.append(paragraph(risk.explanation))
            blocks.extend(
                quote(f'"{citation.quote}" — {citation.clause_id}')
                for statement in risk.statements
                for citation in statement.citations
                if citation.verified
            )
            if risk.question_to_ask:
                blocks.append(paragraph(f"Question to ask: {risk.question_to_ask}"))

    if review.missing:
        blocks.extend(
            [
                heading("Not found in this document", 2),
                paragraph("Not found. Double-check before relying on any of these."),
                bullets([f"{item.title} — {item.why_it_matters}" for item in review.missing]),
            ]
        )

    if review.inconsistencies:
        blocks.extend(
            [
                heading("Places the document disagrees with itself", 2),
                bullets(
                    [f"{entry.title} — {entry.explanation}" for entry in review.inconsistencies]
                ),
            ]
        )
    return blocks


def _answer_blocks(answers: Sequence[AnswerLike]) -> list[Block]:
    """Render the questions asked and what the document said."""
    if not answers:
        return []
    blocks: list[Block] = [heading("Questions asked, and what the document said", 2)]
    for answer in answers:
        blocks.append(paragraph(answer.question))
        statements = answer.statements
        if statements:
            blocks.extend(paragraph(statement.text) for statement in statements)
        else:
            blocks.append(paragraph("This document doesn't say."))
    return blocks


def comparison_document(result: CompareResult, *, title: str, language: str) -> DocumentModel:
    """Build a comparison as a document model.

    The exported table keeps the caption, the impact labels as words and the
    diff markers as words, so nothing depends on colour.

    Args:
        result: The comparison.
        title: Title for the exported file.
        language: BCP 47 tag for the exported file.

    Returns:
        The document model.
    """
    blocks: list[Block] = [heading(title, 1), paragraph(result.caption or "Comparison")]

    if result.mode is CompareMode.VERSIONS:
        rows = [["Clause", "Before", "After", "What changed", "Impact on you"]]
        rows.extend(
            [
                pair.label or "—",
                pair.before_text or "Not in this version",
                pair.after_text or "Not in this version",
                " ".join(statement.text for statement in pair.what_changed) or "Not specified",
                f"{pair.impact or 'Not specified'} ({pair.severity.value} impact)",
            ]
            for pair in result.pairs
        )
    else:
        rows = [["Topic", "Document A", "Document B", "Difference"]]
        rows.extend(
            [
                row.topic,
                " ".join(statement.text for statement in row.a_statements) or "Not specified",
                " ".join(statement.text for statement in row.b_statements) or "Not specified",
                row.difference or "Not specified",
            ]
            for row in result.rows
        )

    blocks.extend([table(rows), Block(type=BlockType.RULE), paragraph(FOOTER)])
    return DocumentModel(title=title, language=language, blocks=blocks)
