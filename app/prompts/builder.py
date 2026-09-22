"""Build prompts. Pure functions, no I/O beyond reading the packaged files once.

Two things matter here and are unit-tested. The document block is assembled so
its delimiters cannot be forged from inside the document, and the pieces are
ordered so the long, identical prefix stays cacheable across calls.
"""

import re
from functools import lru_cache
from typing import Final

from app.adapters.llm.base import (
    CLAUSE_HEADER,
    DOCUMENT_CLOSE,
    DOCUMENT_OPEN,
    Prompt,
    PromptClause,
    Task,
)
from app.config import PROMPTS_DIR
from app.domain.audience import Audience
from app.domain.enums import Language, Role
from app.domain.models import Clause, Document

#: Instruction file per task.
_TASK_FILES: Final[dict[Task, str]] = {
    Task.OVERVIEW: "overview.md",
    Task.REVIEW: "review.md",
    Task.QA: "qa.md",
    Task.SCENARIO: "scenario.md",
    Task.COMPARE: "compare.md",
    Task.LAW_CHANGE: "law_change.md",
    Task.DOC_TYPE: "doc_type.md",
    Task.WORDING: "wording.md",
}

LANGUAGE_NAMES: Final[dict[Language, str]] = {
    Language.EN: "English",
    Language.HI: "Hindi (हिन्दी)",
    Language.MR: "Marathi (मराठी)",
}

ROLE_NAMES: Final[dict[Role, str]] = {
    Role.TENANT: "tenant or licensee",
    Role.LANDLORD: "landlord or licensor",
    Role.EMPLOYEE: "employee",
    Role.EMPLOYER: "employer",
    Role.BORROWER: "borrower",
    Role.LENDER: "lender",
    Role.POLICYHOLDER: "policyholder",
    Role.CUSTOMER: "customer or user",
    Role.NOTICE_RECIPIENT: "person who received this notice",
    Role.OTHER: "reader of this document",
}

#: Anything that looks like the delimiter, however it is spelled or spaced.
_DELIMITER_RE: Final = re.compile(
    r"<\s*/?\s*document\s*>|&lt;\s*/?\s*document\s*&gt;", re.IGNORECASE
)

NEUTRALISED = "[tag removed]"

#: Turns shown to the model when a question follows earlier ones.
MAX_HISTORY_TURNS: Final = 4


@lru_cache(maxsize=len(_TASK_FILES) + 1)
def _read(name: str) -> str:
    """Read one packaged prompt file, once per process."""
    return (PROMPTS_DIR / name).read_text(encoding="utf-8").strip()


def neutralise_delimiters(text: str) -> str:
    """Remove anything that could close or reopen the document block.

    Without this, a document containing ``</document>`` could end the untrusted
    region early and have the rest of its own text read as instructions.

    Args:
        text: Clause text, straight from the document.

    Returns:
        The text with every delimiter-shaped token replaced.
    """
    return _DELIMITER_RE.sub(NEUTRALISED, text)


def build_system_instruction(audience: Audience) -> str:
    """Fill the system instruction for this reader.

    Args:
        audience: The reader's role, language and reading level. Quotes always
            stay in the document's own language, whatever is chosen here.

    Returns:
        The complete system instruction.
    """
    return (
        _read("system.md")
        .replace("{language}", LANGUAGE_NAMES[audience.language])
        .replace("{reading_level}", audience.reading_level.value)
        .replace("{role}", ROLE_NAMES[audience.role])
    )


def build_document_block(clauses: list[Clause]) -> str:
    """Render clauses as the untrusted document block.

    Args:
        clauses: The document's clause map.

    Returns:
        The block, delimiters included, with every clause headed by its id,
        label, page and heading.
    """
    parts = [DOCUMENT_OPEN]
    for clause in clauses:
        parts.append(
            CLAUSE_HEADER.format(
                id=clause.id,
                label=clause.label or "-",
                page=clause.page,
                heading=neutralise_delimiters(clause.heading) or "-",
            )
        )
        parts.append(neutralise_delimiters(clause.text))
    parts.append(DOCUMENT_CLOSE)
    return "\n".join(parts)


def prompt_clauses(clauses: list[Clause]) -> tuple[PromptClause, ...]:
    """Convert clauses to the structured form carried alongside the block."""
    return tuple(
        PromptClause(
            id=clause.id,
            label=clause.label,
            page=clause.page,
            heading=clause.heading,
            text=neutralise_delimiters(clause.text),
        )
        for clause in clauses
    )


def build(
    document: Document,
    task: Task,
    audience: Audience,
    *,
    substitutions: dict[str, str] | None = None,
    question: str = "",
) -> Prompt:
    """Assemble a complete prompt.

    Args:
        document: The document under analysis.
        task: Which analysis to perform.
        audience: The reader's role, language and reading level.
        substitutions: Placeholders to fill in the task instructions.
        question: The reader's own words, placed last.

    Returns:
        The prompt, ordered system, document, instructions, question.
    """
    instructions = _read(_TASK_FILES[task])
    for key, value in (substitutions or {}).items():
        instructions = instructions.replace(f"{{{key}}}", value)

    return Prompt(
        system=build_system_instruction(audience),
        document=build_document_block(document.clauses),
        instructions=instructions,
        question=question,
        clauses=prompt_clauses(document.clauses),
    )


def format_history(turns: list[tuple[str, str]]) -> str:
    """Render recent question-and-answer turns for a follow-up question.

    Args:
        turns: ``(question, answer)`` pairs, oldest first.

    Returns:
        A short transcript, or an empty string when there is no history.
    """
    recent = turns[-MAX_HISTORY_TURNS:]
    if not recent:
        return ""
    lines = ["Earlier in this conversation:"]
    lines.extend(f"Q: {question}\nA: {answer}" for question, answer in recent)
    return "\n".join(lines)
