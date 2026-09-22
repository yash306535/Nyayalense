"""The Get help directory.

Every entry names an official source and the date it was checked, and the UI
shows both. No private lawyers or firms appear, and nothing is ranked or
endorsed.
"""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import DocType, Language, ResourceCategory

Line = Annotated[str, Field(min_length=1, max_length=300)]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]

#: Only https links are shown, so a directory entry can never downgrade a user
#: to an unencrypted connection.
HttpsUrl = Annotated[str, Field(max_length=300, pattern=r"^https://[\w.-]+(/[^\s]*)?$")]

#: Indian helplines are short codes or full numbers; both are dialled as given.
Phone = Annotated[str, Field(max_length=20, pattern=r"^[0-9+][0-9 -]{2,19}$")]


class Contact(BaseModel):
    """How to reach a resource."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    url: HttpsUrl | None = None
    phone: Phone | None = None

    @model_validator(mode="after")
    def _has_a_way_in(self) -> Self:
        """An entry with no way to reach it is not worth showing."""
        if not self.url and not self.phone:
            msg = "a resource needs a URL or a phone number"
            raise ValueError(msg)
        return self


class Resource(BaseModel):
    """One place a person can go for help.

    Attributes:
        relevant_for: Document types, situation keys or detected law acts that
            make this entry worth surfacing after an analysis.
        source_url: The official page the details were read from.
        verified_on: When a person last checked those details.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Annotated[str, Field(min_length=1, max_length=64, pattern=r"^[a-z0-9_]+$")]
    name: Line
    category: ResourceCategory
    purpose: dict[Language, Line]
    contact: Contact
    cost: Line = ""
    hours: Line = ""
    languages: list[Language] = Field(default_factory=list)
    relevant_for: list[Annotated[str, Field(max_length=64)]] = Field(default_factory=list)
    source_url: HttpsUrl
    verified_on: IsoDate

    def purpose_in(self, language: Language) -> str:
        """Return the purpose in a language, falling back to English."""
        return self.purpose.get(language) or self.purpose[Language.EN]

    def is_relevant_to(self, *, doc_type: DocType | None, situations: set[str]) -> bool:
        """Decide whether to surface this entry after an analysis.

        Args:
            doc_type: The document's type, when one is known.
            situations: Situation keys detected from the document or question.

        Returns:
            True when the entry names this document type or one of the situations.
        """
        if not self.relevant_for:
            return True
        keys = set(self.relevant_for)
        return bool(keys & situations) or (doc_type is not None and doc_type.value in keys)


class ResourceDirectory(BaseModel):
    """Every resource NyayaLens ships."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    entries: list[Resource]

    @model_validator(mode="after")
    def _ids_are_unique(self) -> Self:
        """Duplicate ids would make the contextual strip ambiguous."""
        ids = [entry.id for entry in self.entries]
        if len(set(ids)) != len(ids):
            msg = "resource ids must be unique"
            raise ValueError(msg)
        return self

    def relevant(
        self, *, doc_type: DocType | None, situations: set[str], limit: int
    ) -> list[Resource]:
        """Return the entries worth showing after an analysis, most specific first.

        Args:
            doc_type: The document's type, when one is known.
            situations: Situation keys detected from the document or question.
            limit: How many entries to return.

        Returns:
            Up to ``limit`` entries. Free legal aid always qualifies, because it
            is relevant whatever the document turns out to be.
        """
        matched = [
            entry
            for entry in self.entries
            if entry.is_relevant_to(doc_type=doc_type, situations=situations)
        ]
        matched.sort(key=lambda entry: (entry.category is not ResourceCategory.LEGAL_AID,))
        return matched[:limit]
