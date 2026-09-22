"""Word and PDF downloads.

Exports are rate-limited more strictly than reads, because rendering is the
most expensive thing this service does.
"""

from typing import Annotated

from fastapi import APIRouter
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import SettingsDep
from app.api.routes.drafts import require_confirmed
from app.domain.audience import Audience
from app.domain.document_model import DocumentModel
from app.domain.drafting.facts import ConfirmedFacts
from app.domain.enums import ExportFormat, ExportKind
from app.domain.models import Statement
from app.domain.results import CompareResult, Overview, Review
from app.errors import InvalidDocumentError
from app.services.brief import BriefInput, brief_document, comparison_document
from app.services.drafting import build_document, get_template
from app.services.exports import export

router = APIRouter(tags=["drafting"])


class AnswerPayload(BaseModel):
    """One question and the statements that answered it."""

    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, Field(max_length=1000)] = ""
    statements: list[Statement] = Field(default_factory=list)


class BriefPayload(BaseModel):
    """Everything the brief is built from. All of it already verified."""

    model_config = ConfigDict(extra="forbid")

    title: Annotated[str, Field(max_length=300)] = ""
    overview: Overview | None = None
    review: Review | None = None
    answers: list[AnswerPayload] = Field(default_factory=list)
    facts_to_have_ready: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list)
    documents_to_bring: list[Annotated[str, Field(max_length=300)]] = Field(default_factory=list)


class ExportRequest(BaseModel):
    """What to export, and in which format."""

    model_config = ConfigDict(extra="forbid")

    kind: ExportKind
    format: ExportFormat
    audience: Audience = Field(default_factory=Audience)

    template_id: Annotated[str, Field(max_length=64)] = ""
    facts: dict[Annotated[str, Field(max_length=64)], Annotated[str, Field(max_length=2000)]] = (
        Field(default_factory=dict)
    )
    confirmed: bool = Field(
        default=False, description="Whether the user ticked 'I've checked these facts'."
    )

    brief: BriefPayload | None = None
    comparison: CompareResult | None = None


@router.post(
    "/exports",
    summary="Download a Word or PDF file",
    description=(
        "Renders a draft, a brief or a comparison through the one document model the "
        "preview uses, so the file matches the screen. A draft is refused until the user "
        "has confirmed the facts, and every figure is checked against them before the file "
        "is created."
    ),
    response_class=Response,
    responses={
        200: {
            "content": {
                "application/pdf": {},
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document": {},
            },
            "description": "The generated file.",
        }
    },
)
async def create_export(body: ExportRequest, settings: SettingsDep) -> Response:
    """Render and stream one file."""
    document = _build(body)
    file = await export(document, export_format=body.format, settings=settings)
    return Response(
        content=file.content,
        media_type=file.media_type,
        headers={"Content-Disposition": file.disposition},
    )


def _build(body: ExportRequest) -> DocumentModel:
    """Turn the request into a document model.

    Raises:
        InvalidDocumentError: The request did not carry what its kind needs.
        FactsNotConfirmedError: A draft was requested before confirmation.
    """
    if body.kind is ExportKind.DRAFT:
        template = get_template(body.template_id)
        facts = ConfirmedFacts(values=body.facts, confirmed=body.confirmed)
        require_confirmed(facts)
        return build_document(template, facts, language=body.audience.language)

    if body.kind is ExportKind.BRIEF:
        if body.brief is None:
            msg = "No brief was supplied to export."
            raise InvalidDocumentError(msg)
        return brief_document(
            BriefInput(
                title=body.brief.title,
                overview=body.brief.overview,
                review=body.brief.review,
                answers=body.brief.answers,
                language=body.audience.language.value,
                facts_to_have_ready=body.brief.facts_to_have_ready,
                documents_to_bring=body.brief.documents_to_bring,
            )
        )

    if body.comparison is None:
        msg = "No comparison was supplied to export."
        raise InvalidDocumentError(msg)
    title = "Old and new law" if body.kind is ExportKind.LAW_COMPARISON else "Comparison"
    return comparison_document(body.comparison, title=title, language=body.audience.language.value)
