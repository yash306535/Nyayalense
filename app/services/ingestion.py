"""Turn an upload or pasted text into a verified-ready document.

Everything this does is deterministic. No model is called, which means a
document can be read, masked, segmented and checked for internal inconsistencies
before any text has left the process.
"""

import logging
from dataclasses import dataclass, field
from typing import Final

from app.adapters.documents import Extracted, FileKind, extract
from app.adapters.llm.base import LLMClient, Task
from app.adapters.llm.schemas import LLMDocTypeGuess
from app.config import Settings
from app.domain.audience import Audience
from app.domain.definitions import extract_defined_terms
from app.domain.doc_type import guess_doc_type
from app.domain.enums import DocumentWarning, IdentifierKind, Language
from app.domain.laws.models import LawReference
from app.domain.laws.references import find_references
from app.domain.mismatches import find_mismatches
from app.domain.models import AmountMismatch, Clause, Document, MaskedIdentifier
from app.domain.redaction import mask_identifiers
from app.domain.segmentation import segment
from app.errors import InvalidDocumentError
from app.prompts.builder import build
from app.services.cache_keys import document_id

logger = logging.getLogger(__name__)

#: Phrases that mean the document is talking to an AI rather than to a person.
_AI_MARKERS: Final[tuple[str, ...]] = (
    "ai assistant",
    "ai assistants",
    "ai system",
    "language model",
    "ai reviewing",
    "artificial intelligence reviewing",
    "chatbot",
)

#: Devanagari block, used to guess the document's own language.
_DEVANAGARI: Final = range(0x0900, 0x0980)

#: Share of letters that must be Devanagari before the document counts as Hindi
#: or Marathi rather than English.
_DEVANAGARI_SHARE: Final = 0.2

#: Marathi-only words that separate it from Hindi in Devanagari script.
_MARATHI_MARKERS: Final[tuple[str, ...]] = ("आहे", "यांनी", "करार", "मालक", "भाडेकरू", "कलम")


@dataclass(frozen=True, slots=True)
class Ingested:
    """An ingested document and what the user should be told about it.

    Attributes:
        document: The clause map and every deterministic finding.
        masking_note: Sentence describing what was hidden, empty when nothing was.
        law_references: Old- and new-code references found in the text.
    """

    document: Document
    masking_note: str = ""
    law_references: list[LawReference] = field(default_factory=list)


def _detect_language(text: str) -> Language:
    """Guess the language the document is written in."""
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return Language.EN
    devanagari = sum(ord(character) in _DEVANAGARI for character in letters)
    if devanagari / len(letters) < _DEVANAGARI_SHARE:
        return Language.EN
    return Language.MR if any(marker in text for marker in _MARATHI_MARKERS) else Language.HI


def _addresses_ai(clauses: list[Clause]) -> bool:
    """Detect text inside the document aimed at an AI system."""
    haystack = " ".join(clause.text for clause in clauses).casefold()
    return any(marker in haystack for marker in _AI_MARKERS)


def _mask_clauses(clauses: list[Clause]) -> tuple[list[Clause], dict[IdentifierKind, int]]:
    """Mask identifiers in every clause and total what was hidden."""
    masked: list[Clause] = []
    totals: dict[IdentifierKind, int] = {}
    for clause in clauses:
        result = mask_identifiers(clause.text)
        for kind, count in result.counts.items():
            totals[kind] = totals.get(kind, 0) + count
        masked.append(clause.model_copy(update={"text": result.text}))
    return masked, totals


def _mismatches(clauses: list[Clause]) -> list[AmountMismatch]:
    """Find every amount whose words and digits disagree."""
    return [
        AmountMismatch(
            clause_id=clause.id,
            in_words=mismatch.in_words,
            in_digits=mismatch.in_digits,
            words_value=int(mismatch.words_value),
            digits_value=int(mismatch.digits_value),
        )
        for clause in clauses
        for mismatch in find_mismatches(clause.text)
    ]


def _warnings(
    extracted: Extracted, clauses: list[Clause], *, truncated: bool
) -> list[DocumentWarning]:
    """Collect the conditions worth telling the user about."""
    warnings: list[DocumentWarning] = []
    if extracted.needs_ocr:
        warnings.append(DocumentWarning.LITTLE_TEXT)
    if truncated:
        warnings.append(DocumentWarning.TRUNCATED)
    if _addresses_ai(clauses):
        warnings.append(DocumentWarning.ADDRESSES_AI)
    return warnings


def build_document(
    pages: list[str], *, settings: Settings, extracted: Extracted, title: str = ""
) -> Ingested:
    """Segment, mask and inspect extracted text.

    Args:
        pages: Text per page, as extracted.
        settings: Resolved settings supplying the size limits.
        extracted: The extraction result, for its warnings.
        title: Optional document title, normally the file name.

    Returns:
        The document with every deterministic finding attached.

    Raises:
        InvalidDocumentError: No usable text was found.
    """
    truncated = len("\n".join(pages)) > settings.max_document_chars
    if truncated:
        pages = _truncate(pages, settings.max_document_chars)

    clauses = segment(pages)[: settings.max_clauses]
    if not clauses:
        raise InvalidDocumentError(
            "No text could be read from this document. If it is a scan, try a clearer copy, "
            "or paste the text instead."
        )

    masked_clauses, masked_counts = _mask_clauses(clauses)
    document = _assemble(
        masked_clauses,
        masked_counts,
        title=title,
        page_count=max(len(pages), 1),
        warnings=_warnings(extracted, masked_clauses, truncated=truncated),
    )
    references = find_references("\n".join(clause.text for clause in masked_clauses))

    logger.info(
        "document_ingested",
        extra={
            "clauses": len(document.clauses),
            "pages": document.page_count,
            "chars": document.char_count,
            "masked": sum(masked_counts.values()),
            "law_refs": len(references),
            "doc_type": document.doc_type.value,
        },
    )
    return Ingested(document=document, law_references=list(references))


def _assemble(
    clauses: list[Clause],
    masked_counts: dict[IdentifierKind, int],
    *,
    title: str,
    page_count: int,
    warnings: list[DocumentWarning],
) -> Document:
    """Build the document, running every check that needs no model."""
    text = "\n".join(clause.text for clause in clauses)
    guess = guess_doc_type(text)

    return Document(
        id=document_id(clauses),
        doc_type=guess.doc_type,
        doc_type_confidence=guess.confidence,
        language=_detect_language(text),
        clauses=clauses,
        page_count=page_count,
        char_count=len(text),
        title=title[:300],
        warnings=warnings,
        masked=[
            MaskedIdentifier(kind=kind, count=count)
            for kind, count in sorted(masked_counts.items())
        ],
        defined_terms=extract_defined_terms(clauses),
        amount_mismatches=_mismatches(clauses),
        law_reference_ids=[reference.key for reference in find_references(text)],
    )


def _truncate(pages: list[str], limit: int) -> list[str]:
    """Keep whole pages up to the character limit."""
    kept: list[str] = []
    used = 0
    for page in pages:
        if used + len(page) > limit:
            kept.append(page[: max(0, limit - used)])
            break
        kept.append(page)
        used += len(page)
    return kept


def ingest_bytes(data: bytes, *, settings: Settings, title: str = "") -> Ingested:
    """Read an uploaded file and build its document.

    Args:
        data: The uploaded bytes.
        settings: Resolved settings supplying the limits.
        title: Optional document title, normally the file name.

    Returns:
        The ingested document.
    """
    extracted = extract(data, max_pages=settings.max_pages)
    return build_document(extracted.pages, settings=settings, extracted=extracted, title=title)


def ingest_text(text: str, *, settings: Settings, title: str = "") -> Ingested:
    """Build a document from text the user pasted.

    Args:
        text: The pasted text.
        settings: Resolved settings supplying the limits.
        title: Optional document title.

    Returns:
        The ingested document.
    """
    extracted = Extracted(pages=[text], kind=FileKind.TEXT, needs_ocr=False)
    return build_document([text], settings=settings, extracted=extracted, title=title)


async def refine_doc_type(document: Document, client: LLMClient) -> Document:
    """Ask the lite model for a second opinion when the keyword rules were unsure.

    Args:
        document: The freshly ingested document.
        client: The configured model adapter.

    Returns:
        The document, with the type replaced only when the rules were unsure.
    """
    if guess_doc_type("\n".join(clause.text for clause in document.clauses)).is_confident:
        return document

    prompt = build(document, Task.DOC_TYPE, Audience())
    result = await client.generate(prompt, LLMDocTypeGuess, task=Task.DOC_TYPE)
    return document.model_copy(
        update={
            "doc_type": result.data.doc_type,
            "doc_type_confidence": result.data.confidence,
        }
    )
