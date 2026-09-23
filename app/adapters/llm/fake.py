"""A deterministic, document-aware language model.

Demo mode has to be honest, not merely silent: a fake that returned canned
prose would let unverifiable text through and hide exactly the bug the verifier
exists to catch. So this provider only ever quotes text that is really in the
document, picking clauses by word overlap with the task. Every quote it returns
verifies, every answer it cannot support comes back as ``not_found``, and the
browser tests exercise the real pipeline end to end with no network and no key.
"""

import re
import time
from typing import Final

from app.adapters.llm.base import (
    LLMResult,
    LLMUsage,
    Prompt,
    PromptClause,
    ResponseT,
    Task,
    parse_document_block,
)
from app.adapters.llm.schemas import LLMCitation, LLMStatement
from app.constants import MAX_QUOTE_WORDS
from app.domain.enums import (
    StatementKind,
)

_WORD_RE: Final = re.compile(r"[\wऀ-ॿ]+")

_STOPWORDS: Final[frozenset[str]] = frozenset({
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "could", "do", "does",
    "for", "from", "has", "have", "how", "if", "in", "is", "it", "its", "may", "me",
    "my", "not", "of", "on", "or", "shall", "should", "that", "the", "their", "there",
    "these", "this", "to", "was", "what", "when", "where", "which", "who", "will",
    "with", "would", "you", "your",
})  # fmt: skip

#: Shorter words carry too little meaning to rank a clause on.
MIN_WORD_LENGTH: Final = 3

MIN_OVERLAP: Final = 1
MAX_STATEMENTS: Final = 3


def _words(text: str) -> set[str]:
    """Split text into meaningful lowercase words."""
    return {
        word.casefold()
        for word in _WORD_RE.findall(text)
        if len(word) >= MIN_WORD_LENGTH and word.casefold() not in _STOPWORDS
    }


def rank_clauses(clauses: tuple[PromptClause, ...], query: str) -> list[tuple[PromptClause, int]]:
    """Rank clauses by how many query words they contain, best first."""
    wanted = _words(query)
    scored = [
        (clause, len(wanted & _words(f"{clause.heading} {clause.text}"))) for clause in clauses
    ]
    return sorted(
        (entry for entry in scored if entry[1] >= MIN_OVERLAP),
        key=lambda entry: (-entry[1], entry[0].id),
    )


def quote_from(clause: PromptClause, query: str) -> str:
    """Take the most relevant real sentence from a clause, within the word cap."""
    wanted = _words(query)
    sentences = [
        piece.strip() for piece in re.split(r"(?<=[.;।])\s+", clause.text) if piece.strip()
    ]
    best = max(sentences, key=lambda s: (len(wanted & _words(s)), -len(s)), default=clause.text)
    words = best.split()
    return " ".join(words[:MAX_QUOTE_WORDS])


def statement_from(
    text: str, clause: PromptClause, query: str, kind: StatementKind
) -> LLMStatement:
    """Build one statement quoting a clause that really contains the words."""
    return LLMStatement(
        text=text,
        kind=kind,
        citations=[LLMCitation(clause_id=clause.id, quote=quote_from(clause, query))],
    )


def mentions_ai(clauses: tuple[PromptClause, ...]) -> bool:
    """Detect text inside the document that addresses an AI system."""
    haystack = " ".join(clause.text for clause in clauses).casefold()
    return any(
        marker in haystack
        for marker in ("ai assistant", "ai system", "language model", "chatbot", "ai reviewing")
    )


class FakeLLMClient:
    """Offline provider used by tests, ``make dev-fake`` and demo deployments."""

    async def generate(
        self, prompt: Prompt, schema: type[ResponseT], *, task: Task
    ) -> LLMResult[ResponseT]:
        """Produce a schema-valid response grounded in the prompt's own document.

        Args:
            prompt: The prompt that would have gone to a real model.
            schema: The shape the caller expects back.
            task: Which analysis to imitate.

        Returns:
            The parsed response and a usage record marked as the fake model.
        """
        from app.adapters.llm.fake_tasks import BUILDERS  # noqa: PLC0415 - avoids a cycle

        started = time.perf_counter()
        clauses = prompt.clauses or parse_document_block(prompt.document)
        payload = BUILDERS[task](prompt, clauses)
        return LLMResult(
            data=schema.model_validate(payload.model_dump()),
            usage=LLMUsage(
                prompt_tokens=len(prompt.as_text()) // 4,
                output_tokens=len(payload.model_dump_json()) // 4,
                latency_ms=round((time.perf_counter() - started) * 1000, 1),
                model="fake",
            ),
        )


__all__ = [
    "MAX_STATEMENTS",
    "FakeLLMClient",
    "mentions_ai",
    "quote_from",
    "rank_clauses",
    "statement_from",
]
