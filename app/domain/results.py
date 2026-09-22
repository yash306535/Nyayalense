"""Analysis results.

Everything here is what the user finally sees. Each result carries a
:class:`~app.domain.models.VerificationReport`, so the UI can always state how
many statements were checked and how many were dropped.
"""

from pydantic import Field

from app.domain.enums import (
    AnswerType,
    ChangeKind,
    ChecklistStatus,
    CompareMode,
    InconsistencyKind,
    ObligationOwner,
    Role,
    Severity,
    TimingKind,
)
from app.domain.models import (
    Citation,
    Frozen,
    Grounded,
    Identifier,
    ShortText,
    Statement,
    Text,
)


class Answer(Grounded):
    """Result of one grounded question."""

    question: ShortText
    answer_type: AnswerType
    statements: list[Statement] = Field(default_factory=list)
    needs_professional: bool = False
    questions_for_professional: list[ShortText] = Field(default_factory=list)
    suggested_question_to_other_party: ShortText | None = None
    related_clause_ids: list[Identifier] = Field(default_factory=list)


class Party(Frozen):
    """A party as the document names it."""

    name: ShortText
    described_as: ShortText = ""
    is_user: bool = False
    citations: list[Citation] = Field(default_factory=list)


class KeyTerm(Grounded):
    """One commercially important term, or an explicit note that it is absent."""

    id: Identifier
    label: ShortText
    value: ShortText | None = Field(
        default=None, description="None means 'Not specified in this document.'"
    )
    statements: list[Statement] = Field(default_factory=list)

    @property
    def is_specified(self) -> bool:
        """True when the document states this term."""
        return self.value is not None


class Obligation(Frozen):
    """Something one party has to do, and what happens if they do not."""

    who: ObligationOwner
    what: ShortText
    timing: ShortText = ""
    timing_kind: TimingKind = TimingKind.UNSPECIFIED
    consequence: ShortText = ""
    statements: list[Statement] = Field(default_factory=list)


class KeyDate(Frozen):
    """A date the user may want in their calendar."""

    title: ShortText
    date: str = Field(default="", pattern=r"^(\d{4}-\d{2}-\d{2})?$")
    timing_kind: TimingKind = TimingKind.UNSPECIFIED
    description: ShortText = ""
    statements: list[Statement] = Field(default_factory=list)

    @property
    def is_calendarable(self) -> bool:
        """True when this date is absolute enough to become a calendar event."""
        return self.timing_kind is TimingKind.ABSOLUTE and bool(self.date)


class Overview(Grounded):
    """Plain-language summary of the whole document."""

    summary: list[Statement] = Field(default_factory=list)
    parties: list[Party] = Field(default_factory=list)
    key_terms: list[KeyTerm] = Field(default_factory=list)
    obligations: list[Obligation] = Field(default_factory=list)
    key_dates: list[KeyDate] = Field(default_factory=list)
    role: Role = Role.OTHER
    reading_level: str = ""


class ChecklistResult(Frozen):
    """How one curated checklist item fared against this document."""

    item_id: Identifier
    title: ShortText
    status: ChecklistStatus
    statements: list[Statement] = Field(default_factory=list)
    question_to_ask: ShortText = ""


class Risk(Frozen):
    """Something in the document that may work against the user's role."""

    id: Identifier
    category: ShortText
    title: ShortText
    severity: Severity
    explanation: Text
    statements: list[Statement] = Field(default_factory=list)
    question_to_ask: ShortText = ""


class MissingItem(Frozen):
    """A protection the checklist looks for and the document does not appear to have.

    Phrased as an observation, never as certainty: the closest related clause is
    offered so the user can judge for themselves.
    """

    id: Identifier
    title: ShortText
    why_it_matters: Text
    closest_clause_ids: list[Identifier] = Field(default_factory=list)
    question_to_ask: ShortText = ""


class Inconsistency(Frozen):
    """Two parts of the document that do not agree."""

    kind: InconsistencyKind
    title: ShortText
    explanation: Text
    statements: list[Statement] = Field(default_factory=list)


class Review(Grounded):
    """Checklist, risks, missing protections and contradictions for one document."""

    checklist: list[ChecklistResult] = Field(default_factory=list)
    risks: list[Risk] = Field(default_factory=list)
    missing: list[MissingItem] = Field(default_factory=list)
    inconsistencies: list[Inconsistency] = Field(default_factory=list)
    role: Role = Role.OTHER


class ScenarioResult(Grounded):
    """What the document itself says about a hypothetical situation."""

    scenario: ShortText
    says: list[Statement] = Field(default_factory=list)
    consequences: list[Statement] = Field(default_factory=list)
    not_covered: list[ShortText] = Field(default_factory=list)
    next_steps: list[ShortText] = Field(default_factory=list)


class ClausePair(Frozen):
    """Two aligned clauses from different versions of a document."""

    change: ChangeKind
    before_clause_id: Identifier | None = None
    after_clause_id: Identifier | None = None
    label: ShortText = ""
    before_text: str = ""
    after_text: str = ""
    what_changed: list[Statement] = Field(default_factory=list)
    impact: ShortText = ""
    severity: Severity = Severity.LOW


class AlternativeRow(Frozen):
    """One checklist topic compared across two competing documents."""

    topic_id: Identifier
    topic: ShortText
    a_status: ChecklistStatus
    b_status: ChecklistStatus
    a_statements: list[Statement] = Field(default_factory=list)
    b_statements: list[Statement] = Field(default_factory=list)
    difference: ShortText = ""


class CompareResult(Grounded):
    """Outcome of comparing two documents, in either mode."""

    mode: CompareMode
    caption: ShortText = ""
    pairs: list[ClausePair] = Field(default_factory=list)
    rows: list[AlternativeRow] = Field(default_factory=list)
    counts: dict[str, int] = Field(default_factory=dict)
