"""The document and the evidence that backs a claim about it.

These describe what NyayaLens is willing to show a user. They are deliberately
separate from the data-transfer objects a model may return (``app.adapters.llm``):
only :mod:`app.domain.verification` may set :attr:`Citation.verified`, a score or
a span, so a model can never assert that its own quote checks out.

Analysis results built on top of these live in :mod:`app.domain.results`.
"""

from functools import cached_property
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.constants import MAX_QUOTE_WORDS
from app.domain.enums import (
    DocType,
    DocumentWarning,
    IdentifierKind,
    Language,
    RemovalReason,
    StatementKind,
)
from app.domain.normalize import to_nfc

#: Prose that must say something: a statement with no text is not a statement.
Text = Annotated[str, Field(min_length=1, max_length=20_000)]

#: A label or one-liner. May be empty, which means the document states none - a
#: distinction the UI shows as "Not specified in this document."
ShortText = Annotated[str, Field(max_length=500)]
Identifier = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_.:-]+$")]


class Frozen(BaseModel):
    """Base for immutable value objects that reject unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ---------------------------------------------------------------- the document


class Clause(Frozen):
    """One addressable piece of the document.

    Attributes:
        id: Stable identifier, ``C1``..``Cn``, with a letter suffix on split parts.
        label: The document's own numbering, such as ``7.2``. Empty when unnumbered.
        heading: The clause heading, when the document has one.
        text: Clause body, always in Unicode NFC.
        page: 1-based page the clause starts on.
        start: Offset of the clause in the document's full text.
        end: Exclusive end offset of the clause in the document's full text.
    """

    id: Identifier
    label: Annotated[str, Field(max_length=32)] = ""
    heading: Annotated[str, Field(max_length=300)] = ""
    text: Text
    page: Annotated[int, Field(ge=1)] = 1
    start: Annotated[int, Field(ge=0)] = 0
    end: Annotated[int, Field(ge=0)] = 0

    @field_validator("text", "heading")
    @classmethod
    def _store_as_nfc(cls, value: str) -> str:
        """Keep clause text in NFC so verification offsets map to the stored form."""
        return to_nfc(value)

    @property
    def reference(self) -> str:
        """Human-readable location, for example ``Clause 7.2, page 3``."""
        label = f"Clause {self.label}" if self.label else self.id
        return f"{label}, page {self.page}"


class MaskedIdentifier(Frozen):
    """How many identifiers of one kind were hidden before analysis."""

    kind: IdentifierKind
    count: Annotated[int, Field(ge=1)]


class DefinedTerm(Frozen):
    """A term the document defines for itself."""

    term: ShortText
    definition: Text
    clause_id: Identifier


class AmountMismatch(Frozen):
    """A clause whose amount in words differs from its amount in digits."""

    clause_id: Identifier
    in_words: ShortText
    in_digits: ShortText
    words_value: int
    digits_value: int


class Document(Frozen):
    """An ingested document, held by the client and sent with each request.

    The server keeps no copy: this model is the whole shared state, which is why
    it carries its own hash and every deterministic finding made at ingestion.
    """

    id: Identifier = Field(description="SHA-256 of the normalised text, hex, truncated.")
    doc_type: DocType
    doc_type_confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0
    language: Language = Language.EN
    clauses: Annotated[list[Clause], Field(min_length=1, max_length=1500)]
    page_count: Annotated[int, Field(ge=1)] = 1
    char_count: Annotated[int, Field(ge=0)] = 0
    title: Annotated[str, Field(max_length=300)] = ""
    warnings: list[DocumentWarning] = Field(default_factory=list)
    masked: list[MaskedIdentifier] = Field(default_factory=list)
    defined_terms: list[DefinedTerm] = Field(default_factory=list)
    amount_mismatches: list[AmountMismatch] = Field(default_factory=list)
    law_reference_ids: list[Identifier] = Field(
        default_factory=list, description="Ids into the law references found at ingestion."
    )

    @model_validator(mode="after")
    def _clause_ids_are_unique(self) -> Self:
        """Reject a clause map with duplicate ids, which would make citations ambiguous."""
        seen = {clause.id for clause in self.clauses}
        if len(seen) != len(self.clauses):
            msg = "clause ids must be unique"
            raise ValueError(msg)
        return self

    @cached_property
    def by_id(self) -> dict[str, Clause]:
        """Clauses indexed by id. Built once, then reused by the verifier."""
        return {clause.id: clause for clause in self.clauses}

    def clause(self, clause_id: str) -> Clause | None:
        """Return the clause with this id, or ``None`` when there is no such clause."""
        return self.by_id.get(clause_id)

    @property
    def full_text(self) -> str:
        """The document's clauses joined back into one string."""
        return "\n\n".join(clause.text for clause in self.clauses)


# ---------------------------------------------------------------- evidence


class Citation(Frozen):
    """A quote from one clause, and what verification made of it.

    Attributes:
        clause_id: Which clause the quote claims to come from.
        quote: The quoted text, as the model returned it.
        verified: Set only by :mod:`app.domain.verification`.
        score: Match score, 0-100. 100 means an exact substring match.
        span_start: Where the match begins in the clause's stored text.
        span_end: Exclusive end of the match in the clause's stored text.
    """

    clause_id: Identifier
    quote: Annotated[str, Field(min_length=1, max_length=2000)]
    verified: bool = False
    score: Annotated[int, Field(ge=0, le=100)] = 0
    span_start: Annotated[int, Field(ge=0)] = 0
    span_end: Annotated[int, Field(ge=0)] = 0

    @property
    def is_too_long(self) -> bool:
        """True when the quote exceeds the word limit the prompt contract sets."""
        return len(self.quote.split()) > MAX_QUOTE_WORDS


class Statement(Frozen):
    """One claim about the document, with the evidence for it.

    After verification, every statement that survives has at least one verified
    citation, and every figure it mentions appears in one of those quotes.
    """

    text: Text
    kind: StatementKind = StatementKind.DIRECT
    citations: list[Citation] = Field(default_factory=list)

    @property
    def is_supported(self) -> bool:
        """True when at least one citation verified."""
        return any(citation.verified for citation in self.citations)


class RemovedStatement(Frozen):
    """A statement verification dropped, and why.

    Kept so the UI can disclose the removal rather than silently shrinking a
    result.
    """

    reason: RemovalReason
    kind: StatementKind


class VerificationReport(Frozen):
    """What verification did to one result."""

    total: Annotated[int, Field(ge=0)] = 0
    verified: Annotated[int, Field(ge=0)] = 0
    removed: list[RemovedStatement] = Field(default_factory=list)

    @property
    def removed_count(self) -> int:
        """How many statements were dropped.

        A plain property, not a serialised field: the browser sends results back
        with every request, and a field it cannot send back would be rejected.
        The client derives the same number from ``removed``.
        """
        return len(self.removed)

    @property
    def all_verified(self) -> bool:
        """True when nothing had to be removed."""
        return not self.removed and self.total == self.verified


class Grounded(Frozen):
    """Base for every result that carries a verification report."""

    verification: VerificationReport = Field(default_factory=VerificationReport)
