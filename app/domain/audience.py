"""Who a result is being written for.

Role, language and reading level travel together through every prompt and every
service, and together they decide wording and risk severity. They never decide
what counts as evidence: the same document produces the same verified quotes for
every reader.
"""

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Language, ReadingLevel, Role


class Audience(BaseModel):
    """The reader's role, language and preferred level of detail."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Role = Field(default=Role.OTHER, description="Which side of the document you are on.")
    language: Language = Field(default=Language.EN, description="Language for explanations.")
    reading_level: ReadingLevel = Field(
        default=ReadingLevel.SIMPLE, description="How much detail explanations carry."
    )

    def as_params(self) -> dict[str, str]:
        """Render the audience as part of a cache key."""
        return {
            "role": self.role.value,
            "language": self.language.value,
            "reading_level": self.reading_level.value,
        }
