"""The language-model interface every service talks to.

Services depend on this Protocol, never on an SDK. That is what lets the whole
application, including the browser tests, run offline against
:class:`~app.adapters.llm.fake.FakeLLMClient`.
"""

import re
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Protocol, TypeVar

from pydantic import BaseModel

ResponseT = TypeVar("ResponseT", bound=BaseModel)

DOCUMENT_OPEN = "<document>"
DOCUMENT_CLOSE = "</document>"

#: Header line that introduces each clause inside the document block.
CLAUSE_HEADER = "[{id} | {label} | p.{page} | {heading}]"

_CLAUSE_HEADER_RE = re.compile(r"^\[([^|\]]+)\|([^|\]]*)\|\s*p\.(\d+)\s*\|([^\]]*)\]$")


class Task(StrEnum):
    """Which analysis a call performs.

    The real adapter uses this for logging and model selection; the fake uses it
    to decide what shape of answer to build.
    """

    OVERVIEW = "overview"
    REVIEW = "review"
    QA = "qa"
    SCENARIO = "scenario"
    COMPARE = "compare"
    LAW_CHANGE = "law_change"
    DOC_TYPE = "doc_type"
    WORDING = "wording"


@dataclass(frozen=True, slots=True)
class PromptClause:
    """One clause as it appears inside a prompt's document block."""

    id: str
    label: str
    page: int
    heading: str
    text: str


@dataclass(frozen=True, slots=True)
class Prompt:
    """A prompt, in the order that keeps its prefix cacheable.

    The system instruction and the document block are identical across every
    call about one document, so Gemini's implicit context caching can reuse
    those tokens. Anything that varies goes after them.

    Attributes:
        system: The system instruction.
        document: The document block, delimiters included.
        instructions: What to do with the document, for this task.
        question: The user's own words, always last.
        clauses: The same clauses in structured form, for the fake provider.
    """

    system: str
    document: str
    instructions: str
    question: str = ""
    clauses: tuple[PromptClause, ...] = field(default_factory=tuple)

    def as_text(self) -> str:
        """Render the prompt body sent after the system instruction."""
        parts = [self.document, self.instructions]
        if self.question:
            parts.append(f"Question: {self.question}")
        return "\n\n".join(parts)

    @property
    def cacheable_prefix(self) -> str:
        """The part that is identical across calls about the same document."""
        return f"{self.system}\n\n{self.document}"


@dataclass(frozen=True, slots=True)
class LLMUsage:
    """Metadata about one model call. Never contains prompt or response text."""

    prompt_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    latency_ms: float = 0.0
    model: str = ""
    retried: bool = False


@dataclass(frozen=True, slots=True)
class LLMResult[T: BaseModel]:
    """A parsed, schema-valid model response and what the call cost."""

    data: T
    usage: LLMUsage


class LLMClient(Protocol):
    """What every language-model adapter provides."""

    async def generate(
        self, prompt: Prompt, schema: type[ResponseT], *, task: Task
    ) -> LLMResult[ResponseT]:
        """Run one call and parse the response into ``schema``.

        Args:
            prompt: The prompt to send.
            schema: Pydantic model describing the required JSON shape.
            task: Which analysis this call performs.

        Returns:
            The parsed response and the call's usage metadata.

        Raises:
            LLMOutputError: The response did not satisfy the schema, twice.
            UpstreamServiceError: The call failed or timed out.
        """
        ...


def parse_document_block(document: str) -> tuple[PromptClause, ...]:
    """Read a document block back into clauses.

    The fake provider uses this so that it sees exactly what a real model sees,
    which keeps demo mode honest: it can only quote text that is really there.

    Args:
        document: A document block as built by :mod:`app.prompts.builder`.

    Returns:
        The clauses the block contains.
    """
    clauses: list[PromptClause] = []
    current: dict[str, str | int] | None = None
    body: list[str] = []

    for line in document.splitlines():
        header = _CLAUSE_HEADER_RE.match(line.strip())
        if header is not None:
            if current is not None:
                clauses.append(_build(current, body))
            current = {
                "id": header.group(1).strip(),
                "label": header.group(2).strip(),
                "page": int(header.group(3)),
                "heading": header.group(4).strip(),
            }
            body = []
        elif current is not None and line.strip() not in {DOCUMENT_OPEN, DOCUMENT_CLOSE}:
            body.append(line)

    if current is not None:
        clauses.append(_build(current, body))
    return tuple(clauses)


def _build(header: dict[str, str | int], body: list[str]) -> PromptClause:
    """Assemble one clause from a parsed header and its body lines."""
    return PromptClause(
        id=str(header["id"]),
        label=str(header["label"]),
        page=int(header["page"]),
        heading=str(header["heading"]),
        text="\n".join(body).strip(),
    )
