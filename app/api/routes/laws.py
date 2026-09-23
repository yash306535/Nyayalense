"""Old and new criminal laws: lookup, comparison and browsing.

Reference material only. These routes never say which section applies to
anyone's facts, and every row carries its source and review status.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import ContextDep, RegistryDep, SettingsDep
from app.api.schemas import MAX_QUESTION_CHARS
from app.constants import NEW_CODES_IN_FORCE_ON
from app.domain.audience import Audience
from app.domain.enums import ChangeKind, LawAct
from app.domain.laws.models import LawMapping, LawReference, Provision, ProvisionRef
from app.domain.results import Answer
from app.services.laws import answer_legal_question, browse, explain_change, lookup, provision_diff

router = APIRouter(prefix="/laws", tags=["laws"])

MAX_QUERY_CHARS = 120

SOURCE_NOTE = (
    "Correspondence tables published by the Bureau of Police Research & Development, "
    "21 June 2024. They are a police training aid and reference document, not a "
    "statutory instrument."
)

WHEN_EACH_APPLIES = (
    f"The new codes came into force on {NEW_CODES_IN_FORCE_ON}. Conduct before that date "
    "is still charged, tried and appealed under the old codes, and cases already pending "
    "may continue under the old procedure. Ask a lawyer which applies to your situation."
)


class DiffTokenOut(BaseModel):
    """One run of words shared, added or removed between two provision texts."""

    kind: ChangeKind
    text: str


class LookupResponse(BaseModel):
    """What a search of the law data found."""

    model_config = ConfigDict(extra="forbid")

    query: str
    reference: LawReference | None = Field(
        default=None, description="The parsed reference, when the query named an act."
    )
    mappings: list[LawMapping] = Field(
        default_factory=list, description="Matching rows, each with its own source."
    )
    provisions: dict[str, Provision] = Field(
        default_factory=dict, description="Stored texts, keyed 'act:section'. Often empty."
    )
    suggestions: list[str] = Field(
        default_factory=list, description="Near matches, when nothing was found."
    )
    source_note: str = Field(default=SOURCE_NOTE, description="Where these rows come from.")
    when_each_applies: str = Field(
        default=WHEN_EACH_APPLIES, description="Fixed, reviewed copy. Never model output."
    )


class CompareRequest(BaseModel):
    """Which provision to compare across the two codes."""

    model_config = ConfigDict(extra="forbid")

    act: LawAct
    section: Annotated[
        str, Field(min_length=1, max_length=16, pattern=r"^[0-9]{1,3}[A-Za-z]{0,2}$")
    ]
    audience: Audience = Field(default_factory=Audience)


class CompareResponse(LookupResponse):
    """A mapping with the side-by-side comparison, where texts are stored."""

    diff: list[DiffTokenOut] = Field(
        default_factory=list, description="Word-level diff. Empty unless both texts are stored."
    )
    what_changed: Answer | None = Field(
        default=None,
        description=(
            "A verified description of the difference, generated only from the two stored "
            "texts. Null when either text is not packaged."
        ),
    )


@router.get(
    "/lookup",
    response_model=LookupResponse,
    summary="Look up a section",
    description=(
        "Parses a citation in any common form, in English, Hindi or Marathi, and returns "
        "what the official correspondence tables say about it. Works in both directions. "
        "An unknown section returns suggestions, never a guess."
    ),
)
async def lookup_section(
    registry: RegistryDep,
    settings: SettingsDep,
    q: Annotated[
        str, Query(min_length=1, max_length=MAX_QUERY_CHARS, description="e.g. 'IPC 420'")
    ],
) -> LookupResponse:
    """Look up one reference."""
    result = lookup(q, registry.laws, include_unreviewed=settings.law_data_show_unreviewed)
    return LookupResponse(
        query=result.query,
        reference=result.reference,
        mappings=result.mappings,
        provisions=result.provisions,
        suggestions=result.suggestions,
    )


@router.get(
    "/{act}/{section}",
    response_model=LookupResponse,
    summary="Get one provision",
    description="The same as a lookup, addressed directly by act and section.",
)
async def get_provision(
    act: LawAct,
    section: Annotated[str, Field(pattern=r"^[0-9]{1,3}[A-Za-z]{0,2}$")],
    registry: RegistryDep,
    settings: SettingsDep,
) -> LookupResponse:
    """Look up one provision by act and section."""
    return await lookup_section(registry, settings, q=f"{act.value.upper()} {section}")


@router.post(
    "/compare",
    response_model=CompareResponse,
    summary="Compare a provision across the two codes",
    description=(
        "Returns the mapping, a word-level diff of the two texts where both are packaged, "
        "and a description of the difference that has passed the same verifier as every "
        "other explanation. Where a text is not packaged, no description is generated."
    ),
)
async def compare_provision(
    body: CompareRequest, registry: RegistryDep, settings: SettingsDep, context: ContextDep
) -> CompareResponse:
    """Compare one provision across the two codes."""
    result = lookup(
        f"{body.act.value.upper()} {body.section}",
        registry.laws,
        include_unreviewed=settings.law_data_show_unreviewed,
    )
    if not result.mappings:
        return CompareResponse(
            query=result.query, reference=result.reference, suggestions=result.suggestions
        )

    mapping = result.mappings[0]
    old = result.provisions.get(mapping.old.key)
    new = result.provisions.get(mapping.new[0].key) if mapping.new else None

    return CompareResponse(
        query=result.query,
        reference=result.reference,
        mappings=result.mappings,
        provisions=result.provisions,
        diff=[DiffTokenOut(kind=token.kind, text=token.text) for token in provision_diff(old, new)],
        what_changed=await explain_change(
            mapping, result.provisions, audience=body.audience, context=context
        ),
    )


class LegalQuestionRequest(BaseModel):
    """A general legal question, with no document behind it."""

    model_config = ConfigDict(extra="forbid")

    question: Annotated[str, Field(min_length=1, max_length=MAX_QUESTION_CHARS)] = Field(
        description="A general question about the criminal-law codes, e.g. 'What is cheating?'."
    )
    audience: Audience = Field(default_factory=Audience)


class LegalQAResponse(BaseModel):
    """A general legal question, answered from matched statute sections."""

    model_config = ConfigDict(extra="forbid")

    question: str
    matched: list[ProvisionRef] = Field(
        default_factory=list, description="Sections the answer was allowed to draw from."
    )
    answer: Answer


@router.post(
    "/qa",
    response_model=LegalQAResponse,
    summary="Ask a general legal question",
    description=(
        "Answers from real, reviewed sections of the criminal-law codes matched to the "
        "question's own words -- never from a model's memory of what a law says. With no "
        "matching section, or nothing in the matched text that verifies, the answer is "
        "'not_found'. This is general legal information, not advice about your situation."
    ),
)
async def ask_legal_question(body: LegalQuestionRequest, context: ContextDep) -> LegalQAResponse:
    """Answer one general legal question."""
    result = await answer_legal_question(body.question, body.audience, context)
    return LegalQAResponse(question=result.question, matched=result.matched, answer=result.answer)


@router.get(
    "/changes",
    response_model=list[LawMapping],
    summary="Browse notable changes",
    description=(
        "Lists provisions with no counterpart in the new code, or provisions the new code "
        "introduced. Generated from the dataset's own change types."
    ),
)
async def list_changes(
    registry: RegistryDep,
    settings: SettingsDep,
    kind: Annotated[Literal["new", "removed"], Query(description="Which list to return.")],
) -> list[LawMapping]:
    """List one kind of notable change."""
    return browse(registry.laws, kind, include_unreviewed=settings.law_data_show_unreviewed)
