"""Overview and review of a whole document."""

from fastapi import APIRouter

from app.api.deps import ContextDep
from app.api.schemas import DocumentRequest
from app.domain.results import Overview, Review
from app.services.analysis import build_overview, build_review

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post(
    "/overview",
    response_model=Overview,
    summary="Explain the document in plain language",
    description=(
        "Summary, parties, key terms, obligations and key dates. Every statement carries a "
        "verified quote, and a term the document does not specify is returned with no value "
        "rather than a guess."
    ),
)
async def overview(body: DocumentRequest, context: ContextDep) -> Overview:
    """Produce the plain-language overview."""
    return await build_overview(body.document, body.audience, context)


@router.post(
    "/review",
    response_model=Review,
    summary="Review the document against a checklist",
    description=(
        "Fills the curated checklist for this document type, then reports risks for the "
        "chosen role, protections that appear to be missing, and places where the document "
        "contradicts itself."
    ),
)
async def review(body: DocumentRequest, context: ContextDep) -> Review:
    """Produce the checklist, risks, missing protections and contradictions."""
    return await build_review(body.document, body.audience, context)
