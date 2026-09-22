"""Curated review checklists, one per document type.

These are review prompts a careful reader would work through, not legal rules,
and the UI says so. Keeping them as data means adding a document type needs a
JSON file and no code, and the schema below is validated at startup so a
malformed file stops the process instead of reaching a user.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import DocType, Role

Line = Annotated[str, Field(min_length=1, max_length=300)]
ItemId = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")]

MIN_ITEMS = 10
MAX_ITEMS = 15


class Frozen(BaseModel):
    """Immutable value object that rejects unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class ChecklistItem(Frozen):
    """One thing worth checking in a document of this type.

    Attributes:
        id: Stable identifier the model fills a status against.
        title: What to check, as a short noun phrase.
        look_for: Wording that would satisfy this item, to guide the search.
        why_it_matters: Why a reader should care, in plain language.
        question_to_ask: What to ask the other party when it is missing.
        roles: Roles this item applies to. Empty means every role.
    """

    id: ItemId
    title: Line
    look_for: Line
    why_it_matters: Line
    question_to_ask: Line
    roles: list[Role] = Field(default_factory=list)

    def applies_to(self, role: Role) -> bool:
        """True when this item is relevant to the reader's role."""
        return not self.roles or role in self.roles


class Scenario(Frozen):
    """A preset 'what if' the reader can run against the document."""

    id: ItemId
    title: Line


class Checklist(Frozen):
    """Everything curated for one document type."""

    doc_type: DocType
    title: Line
    note: Line = Field(
        default="These are review prompts, not legal rules.",
        description="Shown above the checklist so its status is never overstated.",
    )
    items: list[ChecklistItem]
    suggested_questions: list[Line] = Field(default_factory=list)
    scenarios: list[Scenario] = Field(default_factory=list)
    facts_to_have_ready: list[Line] = Field(default_factory=list)
    documents_to_bring: list[Line] = Field(default_factory=list)

    @model_validator(mode="after")
    def _items_are_sound(self) -> "Checklist":
        """Enforce the size range and unique ids the review prompt depends on."""
        if not MIN_ITEMS <= len(self.items) <= MAX_ITEMS:
            msg = (
                f"{self.doc_type.value}: expected {MIN_ITEMS}-{MAX_ITEMS} checklist items, "
                f"got {len(self.items)}"
            )
            raise ValueError(msg)
        ids = [item.id for item in self.items]
        if len(set(ids)) != len(ids):
            msg = f"{self.doc_type.value}: checklist item ids must be unique"
            raise ValueError(msg)
        return self

    def for_role(self, role: Role) -> list[ChecklistItem]:
        """Return the items relevant to one role."""
        return [item for item in self.items if item.applies_to(role)]

    def as_prompt_lines(self, role: Role) -> str:
        """Render the items for the review prompt.

        Args:
            role: The reader's role, used to drop irrelevant items.

        Returns:
            One ``- id: what to look for`` line per item.
        """
        return "\n".join(
            f"- {item.id}: {item.title}. Look for: {item.look_for}" for item in self.for_role(role)
        )
