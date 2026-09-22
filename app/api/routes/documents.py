"""Ingestion and built-in samples."""

from typing import Annotated

from fastapi import APIRouter, File, Form, UploadFile
from pydantic import BaseModel, Field

from app.api.deps import RegistryDep, SettingsDep
from app.api.schemas import TextRequest
from app.domain.doc_type import default_roles
from app.domain.enums import Role
from app.domain.laws.models import LawReference
from app.domain.models import Document
from app.services.ingestion import Ingested, ingest_bytes, ingest_text

router = APIRouter(tags=["documents"])


class IngestResult(BaseModel):
    """An ingested document and everything found without calling a model."""

    document: Document = Field(description="The clause map. Keep it and send it back.")
    law_references: list[LawReference] = Field(
        default_factory=list, description="Old- and new-code references found in the text."
    )
    suggested_roles: list[Role] = Field(
        default_factory=list, description="Roles to offer first for this document type."
    )


class SampleSummary(BaseModel):
    """One built-in fictional document, for the picker."""

    id: str
    title: str
    description: str


def _result(ingested: Ingested) -> IngestResult:
    """Shape an ingestion result for the API."""
    return IngestResult(
        document=ingested.document,
        law_references=ingested.law_references,
        suggested_roles=list(default_roles(ingested.document.doc_type)),
    )


@router.post(
    "/documents",
    response_model=IngestResult,
    summary="Upload a document",
    description=(
        "Reads a PDF, Word file or text file, segments it into numbered clauses, masks "
        "personal identifiers and reports every finding that needs no model."
    ),
)
async def upload_document(
    settings: SettingsDep,
    file: Annotated[UploadFile, File(description="PDF, DOCX or TXT.")],
    title: Annotated[str, Form()] = "",
) -> IngestResult:
    """Ingest an uploaded file."""
    data = await file.read()
    ingested = ingest_bytes(data, settings=settings, title=title or (file.filename or ""))
    return _result(ingested)


@router.post(
    "/documents/text",
    response_model=IngestResult,
    summary="Paste document text",
    description="Same as uploading a file, for text pasted into the browser.",
)
async def paste_document(body: TextRequest, settings: SettingsDep) -> IngestResult:
    """Ingest pasted text."""
    return _result(ingest_text(body.text, settings=settings, title=body.title))


@router.get(
    "/samples",
    response_model=list[SampleSummary],
    summary="List built-in samples",
    description="Four fictional documents that demonstrate every feature.",
)
async def list_samples(registry: RegistryDep) -> list[SampleSummary]:
    """List the built-in samples."""
    return [
        SampleSummary(id=sample.id, title=sample.title, description=sample.description)
        for sample in registry.samples.values()
    ]


@router.get(
    "/samples/{sample_id}",
    response_model=IngestResult,
    summary="Load a built-in sample",
    description="Ingests one fictional sample and returns it like any other document.",
)
async def load_sample(sample_id: str, registry: RegistryDep, settings: SettingsDep) -> IngestResult:
    """Ingest a built-in sample."""
    sample = registry.sample(sample_id)
    return _result(ingest_text(sample.text, settings=settings, title=sample.title))
