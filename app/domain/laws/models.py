"""Data model for law transitions.

Deliberately generic: an act pair, a table of mappings between their provisions,
and optional stored texts. Adding another transition later means adding data,
not code.
"""

from typing import Annotated, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.domain.enums import ChangeType, LawAct, ReviewStatus

SectionNumber = Annotated[
    str, Field(min_length=1, max_length=16, pattern=r"^[0-9]{1,3}[A-Za-z]{0,2}$")
]
ShortText = Annotated[str, Field(max_length=500)]
IsoDate = Annotated[str, Field(pattern=r"^\d{4}-\d{2}-\d{2}$")]


class Frozen(BaseModel):
    """Immutable value object that rejects unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class LawReference(Frozen):
    """A citation to a statutory provision, as found in a document or a query.

    Attributes:
        act: Which code the reference points at.
        section: The section number, without any sub-section.
        subsection: The sub-section in brackets, when the reference gave one.
        raw: The reference exactly as it was written.
        start: Inclusive offset in the source text.
        end: Exclusive offset in the source text.
    """

    act: LawAct
    section: SectionNumber
    subsection: Annotated[str, Field(max_length=8, pattern=r"^[0-9A-Za-z]*$")] = ""
    raw: Annotated[str, Field(max_length=120)] = ""
    start: Annotated[int, Field(ge=0)] = 0
    end: Annotated[int, Field(ge=0)] = 0

    @property
    def key(self) -> str:
        """Canonical ``act:section`` key used by the lookup index."""
        return f"{self.act.value}:{self.section.upper()}"

    @property
    def display(self) -> str:
        """Reference in a readable form, for example ``IPC 318(4)``."""
        suffix = f"({self.subsection})" if self.subsection else ""
        return f"{self.act.value.upper()} {self.section}{suffix}"


class Source(Frozen):
    """Where a record came from.

    Every mapping row and every stored provision carries one of these, and the
    UI shows it, so no claim about the law is unattributed.
    """

    document: ShortText = Field(description="Title of the source document.")
    page: Annotated[int, Field(ge=0)] = Field(default=0, description="Page, 0 when not paginated.")
    url: Annotated[str, Field(max_length=300, pattern=r"^(https://.*)?$")] = ""


class ProvisionRef(Frozen):
    """One side of a mapping: an act, a section and its title."""

    act: LawAct
    section: SectionNumber
    title: ShortText = ""

    @property
    def key(self) -> str:
        """Canonical ``act:section`` key."""
        return f"{self.act.value}:{self.section.upper()}"

    @property
    def display(self) -> str:
        """Readable reference, for example ``BNS 318``."""
        return f"{self.act.value.upper()} {self.section}"


class LawMapping(Frozen):
    """How one old provision corresponds to the new code.

    Attributes:
        old: The provision in the replaced code.
        new: Its counterparts, empty when there is none.
        change_type: How the two relate.
        note: The source's own remark about the row.
        source: Which document and page the row was read from.
        review_status: Whether a person has checked the row against that source.
        verified_on: Date of that check, empty when unreviewed.
    """

    old: ProvisionRef
    new: list[ProvisionRef] = Field(default_factory=list)
    change_type: ChangeType
    note: ShortText = ""
    source: Source
    review_status: ReviewStatus = ReviewStatus.EXTRACTED
    verified_on: IsoDate | None = None

    @model_validator(mode="after")
    def _counterparts_match_the_change_type(self) -> Self:
        """Keep the row internally consistent so the UI can trust its shape."""
        if self.change_type is ChangeType.NO_DIRECT_EQUIVALENT and self.new:
            msg = "a row with no direct equivalent must list no new provision"
            raise ValueError(msg)
        if self.change_type is not ChangeType.NO_DIRECT_EQUIVALENT and not self.new:
            msg = f"change_type '{self.change_type.value}' requires at least one new provision"
            raise ValueError(msg)
        if self.review_status is ReviewStatus.VERIFIED and not self.verified_on:
            msg = "a verified row must carry the date it was verified"
            raise ValueError(msg)
        return self

    @property
    def is_reviewed(self) -> bool:
        """True when a person has checked this row against the source."""
        return self.review_status is ReviewStatus.VERIFIED


class Provision(Frozen):
    """The stored text of one section, copied from an official source."""

    act: LawAct
    section: SectionNumber
    title: ShortText
    text: Annotated[str, Field(min_length=1, max_length=20_000)]
    source: Source
    review_status: ReviewStatus = ReviewStatus.EXTRACTED
    verified_on: IsoDate | None = None

    @property
    def key(self) -> str:
        """Canonical ``act:section`` key."""
        return f"{self.act.value}:{self.section.upper()}"

    @property
    def display(self) -> str:
        """Readable reference, for example ``IPC 420``."""
        return f"{self.act.value.upper()} {self.section}"


class LawTransition(Frozen):
    """One old act replaced by one new act, and the rows that connect them."""

    id: Annotated[str, Field(min_length=1, max_length=32, pattern=r"^[a-z_]+$")]
    old_act: LawAct
    new_act: LawAct
    old_act_name: ShortText
    new_act_name: ShortText
    in_force_from: IsoDate
    source_note: ShortText
    mappings: list[LawMapping] = Field(default_factory=list)
