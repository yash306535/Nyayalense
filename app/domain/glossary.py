"""General meanings for legal terms.

Used only as a fallback. When the document defines a term itself, that
definition wins and is cited; these entries are always labelled as a general
meaning so the two are never confused.
"""

from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Language

Line = Annotated[str, Field(min_length=1, max_length=400)]


class GlossaryEntry(BaseModel):
    """One term with its meaning in each supported language."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    term: Annotated[str, Field(min_length=1, max_length=80)]
    aliases: list[Annotated[str, Field(max_length=80)]] = Field(default_factory=list)
    meaning: dict[Language, Line]

    def meaning_in(self, language: Language) -> str:
        """Return the meaning in a language, falling back to English."""
        return self.meaning.get(language) or self.meaning[Language.EN]

    def matches(self, word: str) -> bool:
        """True when a word in the document is this term or one of its aliases."""
        lowered = word.casefold()
        return lowered == self.term.casefold() or any(
            lowered == alias.casefold() for alias in self.aliases
        )


class Glossary(BaseModel):
    """Every general meaning NyayaLens ships."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: list[GlossaryEntry]

    def find(self, word: str) -> GlossaryEntry | None:
        """Return the entry for a word, or ``None``."""
        return next((entry for entry in self.entries if entry.matches(word)), None)

    def present_in(self, text: str) -> list[GlossaryEntry]:
        """Return the entries whose term appears in a piece of text."""
        lowered = text.casefold()
        return [
            entry
            for entry in self.entries
            if entry.term.casefold() in lowered
            or any(alias.casefold() in lowered for alias in entry.aliases)
        ]
