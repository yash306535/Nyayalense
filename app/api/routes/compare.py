"""Comparing two documents."""

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ContextDep
from app.domain.audience import Audience
from app.domain.enums import CompareMode
from app.domain.models import Document
from app.domain.results import CompareResult
from app.services.compare import compare_documents

router = APIRouter(tags=["analysis"])


class CompareRequest(BaseModel):
    """Two documents to compare, and how to read them."""

    model_config = ConfigDict(extra="forbid")

    mode: CompareMode = Field(description="Versions of one document, or two competing offers.")
    before: Document = Field(description="The earlier version, or document A.")
    after: Document = Field(description="The later version, or document B.")
    audience: Audience = Field(default_factory=Audience)


@router.post(
    "/compare",
    response_model=CompareResult,
    summary="Compare two documents",
    description=(
        "Aligns clauses deterministically, then asks the model only about the pairs that "
        "actually differ. In the alternatives mode the difference is described neutrally: "
        "NyayaLens does not pick a winner."
    ),
)
async def compare(body: CompareRequest, context: ContextDep) -> CompareResult:
    """Compare two documents."""
    return await compare_documents(
        body.before,
        body.after,
        mode=body.mode,
        audience=body.audience,
        context=context,
    )
