"""What a model is allowed to return.

These are deliberately not the domain models. A model may propose a quote; only
:mod:`app.domain.verification` may decide that the quote checks out. Keeping the
two sets apart makes that impossible to get wrong by accident.

The shapes stay simple on purpose - enums, required fields and lists with empty
defaults, no unions, no recursion, no free-form dictionaries - because that is
what a structured-output schema handles reliably.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import (
    AnswerType,
    ChecklistStatus,
    DocType,
    ObligationOwner,
    Severity,
    StatementKind,
    TimingKind,
)

Line = Annotated[str, Field(max_length=600)]
Body = Annotated[str, Field(max_length=4000)]


class LLMModel(BaseModel):
    """Base for model output: forbid unknown fields so drift is caught at parse time."""

    model_config = ConfigDict(extra="forbid")


class LLMCitation(LLMModel):
    """A quote the model claims comes from a clause. Unverified until checked."""

    clause_id: Annotated[str, Field(max_length=64)] = Field(
        description="Id of the clause the quote is copied from, e.g. 'C12'."
    )
    quote: Annotated[str, Field(max_length=2000)] = Field(
        description="Up to 40 words copied character-for-character from that clause."
    )


class LLMStatement(LLMModel):
    """One claim with its evidence."""

    text: Body = Field(description="The claim, in plain language, numbers written as digits.")
    kind: StatementKind = Field(
        description="'direct' if the text states it, else 'interpretation'."
    )
    citations: list[LLMCitation] = Field(
        default_factory=list, description="At least one citation supporting this claim."
    )


class LLMAnswer(LLMModel):
    """Answer to one question about the document."""

    answer_type: AnswerType
    statements: list[LLMStatement] = Field(default_factory=list)
    needs_professional: bool = Field(
        default=False, description="True when answering properly needs legal judgement."
    )
    questions_for_professional: list[Line] = Field(default_factory=list)
    suggested_question_to_other_party: Line = Field(
        default="", description="For a not_found answer: what to ask the other party instead."
    )
    related_clause_ids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list)
    injection_warning: bool = Field(
        default=False, description="True when the document contains text addressed to an AI system."
    )


class LLMParty(LLMModel):
    """A party as the document names it."""

    name: Line
    described_as: Line = ""
    is_user: bool = False
    citations: list[LLMCitation] = Field(default_factory=list)


class LLMKeyTerm(LLMModel):
    """A commercially important term, or an empty value meaning it is absent."""

    id: Annotated[str, Field(max_length=64)]
    label: Line
    value: Line = Field(default="", description="Empty when the document does not specify it.")
    statements: list[LLMStatement] = Field(default_factory=list)


class LLMObligation(LLMModel):
    """Something a party must do."""

    who: ObligationOwner
    what: Line
    timing: Line = ""
    timing_kind: TimingKind = TimingKind.UNSPECIFIED
    consequence: Line = ""
    statements: list[LLMStatement] = Field(default_factory=list)


class LLMKeyDate(LLMModel):
    """A date that matters, absolute where the document gives one."""

    title: Line
    date: Annotated[str, Field(max_length=10)] = Field(
        default="", description="ISO yyyy-mm-dd, empty unless the document states a calendar date."
    )
    timing_kind: TimingKind = TimingKind.UNSPECIFIED
    description: Line = ""
    statements: list[LLMStatement] = Field(default_factory=list)


class LLMOverview(LLMModel):
    """Plain-language description of the whole document."""

    summary: list[LLMStatement] = Field(default_factory=list)
    parties: list[LLMParty] = Field(default_factory=list)
    key_terms: list[LLMKeyTerm] = Field(default_factory=list)
    obligations: list[LLMObligation] = Field(default_factory=list)
    key_dates: list[LLMKeyDate] = Field(default_factory=list)
    injection_warning: bool = False


class LLMChecklistResult(LLMModel):
    """How the document fares against one curated checklist item."""

    item_id: Annotated[str, Field(max_length=64)]
    status: ChecklistStatus
    statements: list[LLMStatement] = Field(default_factory=list)
    closest_clause_ids: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list)


class LLMRisk(LLMModel):
    """Something in the document that may work against the reader."""

    category: Line
    title: Line
    severity: Severity
    explanation: Body
    statements: list[LLMStatement] = Field(default_factory=list)
    question_to_ask: Line = ""


class LLMContradiction(LLMModel):
    """Two clauses that do not agree. Needs a quote from each."""

    title: Line
    explanation: Body
    statements: list[LLMStatement] = Field(default_factory=list)


class LLMReview(LLMModel):
    """Checklist outcomes, risks and contradictions for one document."""

    checklist: list[LLMChecklistResult] = Field(default_factory=list)
    risks: list[LLMRisk] = Field(default_factory=list)
    contradictions: list[LLMContradiction] = Field(default_factory=list)
    injection_warning: bool = False


class LLMScenario(LLMModel):
    """What the document itself says about a hypothetical situation."""

    says: list[LLMStatement] = Field(default_factory=list)
    consequences: list[LLMStatement] = Field(default_factory=list)
    not_covered: list[Line] = Field(default_factory=list)
    next_steps: list[Line] = Field(default_factory=list)


class LLMChangeExplanation(LLMModel):
    """What changed between two versions of one clause, and why it matters."""

    clause_label: Line = ""
    statements: list[LLMStatement] = Field(default_factory=list)
    impact: Line = ""
    severity: Severity = Severity.LOW


class LLMCompare(LLMModel):
    """Explanations for every changed clause pair in a comparison."""

    changes: list[LLMChangeExplanation] = Field(default_factory=list)


class LLMDocTypeGuess(LLMModel):
    """Fallback document-type guess, used only when keyword rules are unsure."""

    doc_type: DocType
    confidence: Annotated[float, Field(ge=0.0, le=1.0)] = 0.0


class LLMWording(LLMModel):
    """Suggested wording for one free-text field.

    The text may refer to facts only through ``[[slot]]`` tokens. Code fills
    those from the user's confirmed facts, so the model never types a fact.
    """

    text: Body = Field(description="Formal wording using [[slot]] tokens for every fact.")
    slots_used: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list)
