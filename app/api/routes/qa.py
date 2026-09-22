"""Grounded question answering."""

from fastapi import APIRouter

from app.api.deps import ContextDep
from app.api.schemas import QuestionRequest
from app.domain.results import Answer
from app.services.qa import answer_question

router = APIRouter(tags=["ask"])


@router.post(
    "/qa",
    response_model=Answer,
    summary="Ask a question about the document",
    description=(
        "Answers using only the document. When the document does not answer, the result is "
        "'not_found' with a question to put to the other party, never a guess."
    ),
)
async def ask(body: QuestionRequest, context: ContextDep) -> Answer:
    """Answer one question about the document."""
    return await answer_question(
        body.document,
        body.question,
        body.audience,
        context,
        history=[(turn.question, turn.answer) for turn in body.history],
    )
