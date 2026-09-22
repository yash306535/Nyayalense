"""Clearing a document's cached results."""

from typing import Annotated

from fastapi import APIRouter, Path
from pydantic import BaseModel, Field

from app.api.deps import CacheDep

router = APIRouter(tags=["meta"])


class Cleared(BaseModel):
    """How many cached results were removed."""

    removed: int = Field(description="Number of cached entries dropped.")


@router.delete(
    "/cache/{document_hash}",
    response_model=Cleared,
    summary="Clear a document's cached results",
    description=(
        "Backs the 'Clear this document' button. Removes every cached analysis for one "
        "document. Nothing durable is stored, so this is the only server-side state there "
        "is to clear."
    ),
)
async def clear_cache(
    document_hash: Annotated[str, Path(min_length=8, max_length=64, pattern=r"^[a-f0-9]+$")],
    cache: CacheDep,
) -> Cleared:
    """Drop every cached result for one document."""
    return Cleared(removed=cache.purge(f"{document_hash}:"))
