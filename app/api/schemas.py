"""Request bodies shared by more than one route.

Because the API is stateless, the browser sends the clause map back with every
analysis request. These models cap its size so a request can never make the
server hold more than it agreed to.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.domain.audience import Audience
from app.domain.models import Document

MAX_QUESTION_CHARS = 1000
MAX_HISTORY_TURNS = 4


class DocumentRequest(BaseModel):
    """A request carrying the client-held document."""

    model_config = ConfigDict(extra="forbid")

    document: Document = Field(description="The clause map returned by ingestion.")
    audience: Audience = Field(default_factory=Audience)


class Turn(BaseModel):
    """One earlier question and the answer that was given."""

    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, Field(max_length=MAX_QUESTION_CHARS)]
    answer: Annotated[str, Field(max_length=4000)]


class QuestionRequest(DocumentRequest):
    """A question about the document, with recent turns for follow-ups."""

    question: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_CHARS)] = Field(
        description="What you want to know about this document."
    )
    history: Annotated[list[Turn], Field(max_length=MAX_HISTORY_TURNS)] = Field(
        default_factory=list, description="Up to four earlier turns, oldest first."
    )


class TextRequest(BaseModel):
    """Pasted document text."""

    model_config = ConfigDict(extra="forbid")

    text: Annotated[str, Field(min_length=1, max_length=400_000)] = Field(
        description="The document text, pasted."
    )
    title: Annotated[str, Field(max_length=300)] = ""
