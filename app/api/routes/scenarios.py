"""What-if scenarios."""

from typing import Annotated

from fastapi import APIRouter
from pydantic import Field

from app.api.deps import ContextDep
from app.api.schemas import DocumentRequest
from app.domain.results import ScenarioResult
from app.services.scenarios import run_scenario

router = APIRouter(tags=["analysis"])

MAX_SCENARIO_CHARS = 500


class ScenarioRequest(DocumentRequest):
    """A situation to work through against the document."""

    scenario: Annotated[str, Field(min_length=1, max_length=MAX_SCENARIO_CHARS)] = Field(
        description="A preset scenario, or one the reader typed."
    )


@router.post(
    "/scenarios",
    response_model=ScenarioResult,
    summary="Work through a what-if",
    description=(
        "Reports what the document says about a situation and any consequence the document "
        "itself states. It never predicts what a court would do, and it says plainly when "
        "the document does not cover the situation."
    ),
)
async def scenario(body: ScenarioRequest, context: ContextDep) -> ScenarioResult:
    """Run one what-if."""
    return await run_scenario(body.document, body.scenario, audience=body.audience, context=context)
