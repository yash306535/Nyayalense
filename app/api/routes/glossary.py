"""General meanings for legal terms."""

from fastapi import APIRouter

from app.api.deps import RegistryDep
from app.domain.glossary import GlossaryEntry

router = APIRouter(tags=["reference data"])


@router.get(
    "/glossary",
    response_model=list[GlossaryEntry],
    summary="Get the general meanings of legal terms",
    description=(
        "Reviewed general meanings in English, Hindi and Marathi. These are a fallback: "
        "where the document defines a term itself, that definition wins and is shown with "
        "the clause it came from. A general meaning is always labelled as one."
    ),
)
async def list_glossary(registry: RegistryDep) -> list[GlossaryEntry]:
    """Return every packaged glossary entry."""
    return registry.glossary.entries
