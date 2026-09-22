"""The curated checklists, served as data."""

from fastapi import APIRouter

from app.api.deps import RegistryDep
from app.domain.checklists import Checklist
from app.domain.enums import DocType

router = APIRouter(tags=["reference data"])


@router.get(
    "/checklists/{doc_type}",
    response_model=Checklist,
    summary="Get the checklist for a document type",
    description=(
        "The items a careful reader would work through, plus suggested questions, preset "
        "what-if scenarios, and what to have ready for a lawyer. These are review prompts, "
        "not legal rules."
    ),
)
async def get_checklist(doc_type: DocType, registry: RegistryDep) -> Checklist:
    """Return one curated checklist."""
    return registry.checklist(doc_type)
