"""The facts sheet: typed fields, validation and deterministic prefill."""

import re
from datetime import date
from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import FieldType, Language

Line = Annotated[str, Field(max_length=300)]
FieldName = Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]

DEFAULT_MAX_LENGTH = 300
MULTILINE_MAX_LENGTH = 2000

#: Patterns each field type must satisfy. A field the user can type into is a
#: field an attacker can type into, so every value is checked before rendering.
_PATTERNS: dict[FieldType, re.Pattern[str]] = {
    FieldType.DATE: re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    FieldType.MONEY: re.compile(r"^[\d,]+(\.\d{1,2})?$"),
    FieldType.EMAIL: re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$"),
    FieldType.PHONE: re.compile(r"^[0-9+][0-9 \-]{5,19}$"),
}


class FactField(BaseModel):
    """One field of a letter template's facts sheet.

    Attributes:
        prefill_from: Where a value may be taken from a verified result, such as
            ``key_term.deposit``. Prefilled values always show their citation
            and the user can change any of them.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: FieldName
    type: FieldType = FieldType.TEXT
    required: bool = True
    max_length: Annotated[int, Field(ge=1, le=MULTILINE_MAX_LENGTH)] = DEFAULT_MAX_LENGTH
    pattern: Annotated[str, Field(max_length=200)] = ""
    choices: list[Line] = Field(default_factory=list)
    labels: dict[Language, Line]
    help: dict[Language, Line] = Field(default_factory=dict)
    prefill_from: Annotated[str, Field(max_length=64)] = ""

    @model_validator(mode="after")
    def _choices_match_the_type(self) -> Self:
        """A choice field without choices would render an empty select."""
        if self.type is FieldType.CHOICE and not self.choices:
            msg = f"field '{self.name}' is a choice field but lists no choices"
            raise ValueError(msg)
        return self

    def label_in(self, language: Language) -> str:
        """Return the label in a language, falling back to English."""
        return self.labels.get(language) or self.labels[Language.EN]

    def validate_value(self, value: str) -> str | None:
        """Check one submitted value.

        Args:
            value: What the user typed.

        Returns:
            An error message, or ``None`` when the value is acceptable.
        """
        text = value.strip()
        if not text:
            return "This is required." if self.required else None

        pattern = _PATTERNS.get(self.type)
        checks: tuple[tuple[bool, str], ...] = (
            (
                len(text) > self.max_length,
                f"Keep this to {self.max_length} characters or fewer.",
            ),
            (
                self.type is FieldType.CHOICE and text not in self.choices,
                "Choose one of the options.",
            ),
            (pattern is not None and not pattern.match(text), _format_hint(self.type)),
            (
                bool(self.pattern) and not re.match(self.pattern, text),
                "This does not look right. Check the format.",
            ),
            (self.type is FieldType.DATE and not _is_real_date(text), "That date does not exist."),
        )
        return next((message for failed, message in checks if failed), None)


def _format_hint(field_type: FieldType) -> str:
    """Return a message saying how to fix a badly formatted value."""
    hints = {
        FieldType.DATE: "Use the date picker, or write the date as yyyy-mm-dd.",
        FieldType.MONEY: "Write the amount in digits, for example 60000 or 60,000.",
        FieldType.EMAIL: "Write a full email address, for example name@example.com.",
        FieldType.PHONE: "Write the phone number in digits, with or without the country code.",
    }
    return hints.get(field_type, "This does not look right. Check the format.")


def _is_real_date(text: str) -> bool:
    """Check that an ISO date names a day that exists."""
    try:
        date.fromisoformat(text)
    except ValueError:
        return False
    return True


class DraftTemplate(BaseModel):
    """A letter template: its fields, its title and the slots its wording may use."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$")]
    title: Line
    description: Line = ""
    doc_types: list[str] = Field(default_factory=list)
    fields: Annotated[list[FactField], Field(min_length=1)]
    wording_field: FieldName | None = Field(
        default=None, description="The free-text field model wording may be offered for."
    )
    required_slots: list[FieldName] = Field(default_factory=list)

    @model_validator(mode="after")
    def _names_are_unique_and_slots_exist(self) -> Self:
        """Keep field names unique and every named slot real."""
        names = [field.name for field in self.fields]
        if len(set(names)) != len(names):
            msg = f"template '{self.id}' has duplicate field names"
            raise ValueError(msg)
        unknown = set(self.required_slots) - set(names)
        if unknown:
            msg = f"template '{self.id}' requires unknown slots: {', '.join(sorted(unknown))}"
            raise ValueError(msg)
        if self.wording_field and self.wording_field not in names:
            msg = f"template '{self.id}' names an unknown wording field"
            raise ValueError(msg)
        return self

    def field(self, name: str) -> FactField | None:
        """Return one field by name."""
        return next((field for field in self.fields if field.name == name), None)

    @property
    def slot_names(self) -> set[str]:
        """Every field name that may appear as a slot token."""
        return {field.name for field in self.fields}


class ConfirmedFacts(BaseModel):
    """The facts a user has checked and agreed to."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    values: dict[FieldName, Annotated[str, Field(max_length=MULTILINE_MAX_LENGTH)]] = Field(
        default_factory=dict
    )
    confirmed: bool = Field(
        default=False, description="Set when the user ticks 'I've checked these facts'."
    )

    def get(self, name: str) -> str:
        """Return one value, or an empty string."""
        return self.values.get(name, "")


def validate_facts(template: DraftTemplate, facts: ConfirmedFacts) -> dict[str, str]:
    """Validate every field of a facts sheet.

    Args:
        template: The template being filled.
        facts: What the user entered.

    Returns:
        Error messages keyed by field name. Empty when everything is acceptable.
    """
    errors: dict[str, str] = {}
    for field in template.fields:
        error = field.validate_value(facts.get(field.name))
        if error:
            errors[field.name] = error
    unknown = set(facts.values) - template.slot_names
    for name in unknown:
        errors[name] = "This is not a field of this template."
    return errors
