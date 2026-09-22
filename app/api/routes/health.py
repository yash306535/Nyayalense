"""Liveness probe."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(tags=["meta"])


class Health(BaseModel):
    """Liveness result."""

    status: Literal["ok"] = Field(description="Always 'ok' when the process is serving.")


@router.get(
    "/healthz",
    response_model=Health,
    summary="Liveness probe",
    description="Returns 200 as soon as the process can serve requests.",
)
async def healthz() -> Health:
    """Report that the process is alive."""
    return Health(status="ok")
