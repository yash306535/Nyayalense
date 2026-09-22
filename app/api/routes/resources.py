"""The Get help directory."""

from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import RegistryDep
from app.domain.enums import DocType
from app.domain.resources import Resource

router = APIRouter(tags=["reference data"])

DEFAULT_LIMIT = 20
CONTEXTUAL_LIMIT = 3


@router.get(
    "/resources",
    response_model=list[Resource],
    summary="Get help: official places to go",
    description=(
        "Free legal aid and official complaint routes. Every entry names the official source "
        "it was read from and the date it was checked. No private lawyers or firms, and "
        "nothing is ranked or endorsed."
    ),
)
async def list_resources(
    registry: RegistryDep,
    doc_type: Annotated[DocType | None, Query(description="Narrow to one document type.")] = None,
    situation: Annotated[
        list[str] | None, Query(description="Situation keys, such as 'online_fraud'.")
    ] = None,
    contextual: Annotated[
        bool, Query(description="Return only the two or three most relevant entries.")
    ] = False,
) -> list[Resource]:
    """Return the directory, optionally narrowed to a document or situation."""
    if doc_type is None and not situation and not contextual:
        return registry.resources.entries
    return registry.resources.relevant(
        doc_type=doc_type,
        situations=set(situation or []),
        limit=CONTEXTUAL_LIMIT if contextual else DEFAULT_LIMIT,
    )
