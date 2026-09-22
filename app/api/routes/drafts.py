"""Letter templates, prefill and the live preview."""

from typing import Annotated

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ContextDep, SettingsDep
from app.domain.audience import Audience
from app.domain.document_model import DocumentModel
from app.domain.drafting.facts import ConfirmedFacts, DraftTemplate
from app.domain.enums import DocType
from app.domain.models import Document
from app.domain.results import Overview
from app.errors import FactsNotConfirmedError
from app.services.drafting import (
    build_document,
    field_errors,
    get_template,
    map_prefill,
    prefill,
    suggest_wording,
    templates_for,
)

router = APIRouter(prefix="/drafts", tags=["drafting"])


class PrefillRequest(BaseModel):
    """Ask for the facts that can be taken from verified results."""

    model_config = ConfigDict(extra="forbid")

    template_id: Annotated[str, Field(max_length=64)]
    document: Document
    overview: Overview | None = None


class PrefillResponse(BaseModel):
    """Prefilled values, each with the clause it came from."""

    values: dict[str, str] = Field(default_factory=dict)
    sources: dict[str, dict[str, str]] = Field(
        default_factory=dict, description="Clause label and page behind each prefilled value."
    )


class PreviewRequest(BaseModel):
    """Render the letter from the facts entered so far."""

    model_config = ConfigDict(extra="forbid")

    template_id: Annotated[str, Field(max_length=64)]
    facts: dict[Annotated[str, Field(max_length=64)], Annotated[str, Field(max_length=2000)]] = (
        Field(default_factory=dict)
    )
    audience: Audience = Field(default_factory=Audience)
    wording_draft: Annotated[str, Field(max_length=2000)] = ""
    want_wording: bool = False


class PreviewResponse(BaseModel):
    """The rendered letter plus the reports that gate the download."""

    document: DocumentModel
    errors: dict[str, str] = Field(
        default_factory=dict, description="Validation messages keyed by field name."
    )
    wording: str = Field(default="", description="Wording to use for the free-text field.")
    wording_rejected: bool = Field(
        default=False,
        description="True when the model's suggestion broke the slot contract and was dropped.",
    )


@router.get(
    "/templates",
    response_model=list[DraftTemplate],
    summary="List letter templates",
    description=(
        "Each template declares its own fields, so adding one needs a data file and no "
        "code change. Titles say 'letter' or 'request', never 'legal notice'."
    ),
)
async def list_templates(
    doc_type: DocType | None = None,
) -> list[DraftTemplate]:
    """List the templates, optionally narrowed to a document type."""
    return templates_for(doc_type)


@router.post(
    "/prefill",
    response_model=PrefillResponse,
    summary="Prefill a facts sheet from verified results",
    description=(
        "Fills only what a verified result already contains, and returns the clause behind "
        "each value so the user can check it. Every value stays editable."
    ),
)
async def prefill_facts(body: PrefillRequest) -> PrefillResponse:
    """Prefill what can be prefilled."""
    template = get_template(body.template_id)
    available, sources = prefill(body.document, body.overview)
    values = map_prefill(template, available)
    return PrefillResponse(
        values=values,
        sources={
            field.name: sources[field.prefill_from]
            for field in template.fields
            if field.prefill_from in sources and field.name in values
        },
    )


@router.post(
    "/preview",
    response_model=PreviewResponse,
    summary="Preview the letter",
    description=(
        "Renders the letter into the same document model the Word file and the PDF are "
        "built from, so the preview is the file. Every figure is checked against the "
        "confirmed facts before the model is returned."
    ),
)
async def preview(
    body: PreviewRequest, context: ContextDep, settings: SettingsDep
) -> PreviewResponse:
    """Render the live preview."""
    del settings
    template = get_template(body.template_id)
    facts = ConfirmedFacts(values=body.facts)
    errors = field_errors(template, facts)

    wording = body.wording_draft
    rejected = False
    if body.want_wording and body.wording_draft:
        wording, rejected = await suggest_wording(
            template, body.wording_draft, facts, audience=body.audience, context=context
        )
        if template.wording_field:
            facts = ConfirmedFacts(values={**facts.values, template.wording_field: wording})

    # A missing required fact is a form error, not a render failure, so the
    # preview still shows what is there with the gaps left blank.
    filled = ConfirmedFacts(values={field.name: facts.get(field.name) for field in template.fields})
    document = build_document(template, filled, language=body.audience.language)

    return PreviewResponse(
        document=document, errors=errors, wording=wording, wording_rejected=rejected
    )


def require_confirmed(facts: ConfirmedFacts) -> None:
    """Refuse to export facts the user has not confirmed.

    Raises:
        FactsNotConfirmedError: The confirmation box was not ticked.
    """
    if not facts.confirmed:
        msg = "Tick 'I've checked these facts' before downloading."
        raise FactsNotConfirmedError(msg)
