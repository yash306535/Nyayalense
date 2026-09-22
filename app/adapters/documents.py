"""Read text out of an uploaded file.

Everything here is defensive. The file type is decided by its bytes rather than
its name, size and page limits are enforced before the expensive work, and a zip
archive is inspected before it is expanded. Nothing is written to disk.
"""

import io
import zipfile
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

import pdfplumber
from docx import Document as DocxDocument

from app.errors import (
    DocumentTooLargeError,
    EncryptedDocumentError,
    InvalidDocumentError,
    UnsupportedFileTypeError,
)

PDF_MAGIC: Final = b"%PDF-"
ZIP_MAGIC: Final = b"PK\x03\x04"
PNG_MAGIC: Final = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC: Final = b"\xff\xd8\xff"

#: Marker that tells a DOCX apart from any other zip archive.
DOCX_MARKER: Final = "[Content_Types].xml"

#: A DOCX whose contents expand by more than this is treated as a zip bomb.
MAX_EXPANSION_RATIO: Final = 120

#: Absolute ceiling on expanded DOCX contents, regardless of ratio.
MAX_EXPANDED_BYTES: Final = 80 * 1024 * 1024

#: Below this many characters a document is probably a scan.
MIN_USEFUL_CHARS: Final = 200

#: Control characters below TAB never appear in text, only in binary formats.
_FIRST_PRINTABLE_CONTROL: Final = 9


class FileKind(StrEnum):
    """File types the reader accepts."""

    PDF = "pdf"
    DOCX = "docx"
    TEXT = "txt"
    PNG = "png"
    JPEG = "jpeg"


@dataclass(frozen=True, slots=True)
class Extracted:
    """Text pulled out of a file, one entry per page.

    Attributes:
        pages: Text per page. A DOCX or a text file yields a single page.
        kind: What the bytes turned out to be.
        needs_ocr: True when there is too little text to work with.
    """

    pages: list[str]
    kind: FileKind
    needs_ocr: bool = False

    @property
    def char_count(self) -> int:
        """Total characters extracted."""
        return sum(len(page) for page in self.pages)


def detect_kind(data: bytes) -> FileKind:
    """Decide a file's type from its leading bytes.

    Args:
        data: The uploaded bytes.

    Returns:
        The detected type.

    Raises:
        UnsupportedFileTypeError: The bytes match no accepted format.
    """
    if data.startswith(PDF_MAGIC):
        return FileKind.PDF
    if data.startswith(PNG_MAGIC):
        return FileKind.PNG
    if data.startswith(JPEG_MAGIC):
        return FileKind.JPEG
    if data.startswith(ZIP_MAGIC):
        return _zip_kind(data)
    if _looks_like_text(data):
        return FileKind.TEXT
    raise UnsupportedFileTypeError(
        "Upload a PDF, Word file, image or plain text file, or paste the text instead."
    )


def _zip_kind(data: bytes) -> FileKind:
    """Confirm a zip archive is really a Word document."""
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if DOCX_MARKER not in archive.namelist():
                raise UnsupportedFileTypeError("This looks like a zip file, not a Word document.")
            _guard_zip_bomb(archive, len(data))
    except zipfile.BadZipFile as error:
        raise InvalidDocumentError("This file is damaged and could not be opened.") from error
    return FileKind.DOCX


def _guard_zip_bomb(archive: zipfile.ZipFile, compressed_size: int) -> None:
    """Refuse an archive that expands far beyond its compressed size.

    Raises:
        DocumentTooLargeError: The archive expands past either limit.
    """
    expanded = sum(entry.file_size for entry in archive.infolist())
    if expanded > MAX_EXPANDED_BYTES or expanded > compressed_size * MAX_EXPANSION_RATIO:
        raise DocumentTooLargeError(
            "This Word file expands to far more than its size suggests, so it was not opened."
        )


def _looks_like_text(data: bytes) -> bool:
    """Check whether the bytes decode as UTF-8 without control characters."""
    try:
        decoded = data.decode("utf-8")
    except UnicodeDecodeError:
        return False
    return not any(ord(character) < _FIRST_PRINTABLE_CONTROL for character in decoded)


def extract(data: bytes, *, max_pages: int) -> Extracted:
    """Extract text from an uploaded file.

    Args:
        data: The uploaded bytes.
        max_pages: Largest page count accepted.

    Returns:
        The text, per page, with the detected type.

    Raises:
        UnsupportedFileTypeError: The bytes match no accepted format.
        DocumentTooLargeError: The file has more pages than allowed.
        EncryptedDocumentError: The PDF is password-protected.
        InvalidDocumentError: The file could not be parsed.
    """
    kind = detect_kind(data)
    if kind is FileKind.PDF:
        return _extract_pdf(data, max_pages=max_pages)
    if kind is FileKind.DOCX:
        return _extract_docx(data)
    if kind is FileKind.TEXT:
        return _extract_text(data)
    return Extracted(pages=[], kind=kind, needs_ocr=True)


def _extract_pdf(data: bytes, *, max_pages: int) -> Extracted:
    """Read a text PDF page by page."""
    try:
        with pdfplumber.open(io.BytesIO(data)) as pdf:
            if len(pdf.pages) > max_pages:
                raise DocumentTooLargeError(
                    f"This PDF has {len(pdf.pages)} pages. "
                    f"NyayaLens reads up to {max_pages}. Split it and upload the part you need."
                )
            pages = [page.extract_text() or "" for page in pdf.pages]
    except DocumentTooLargeError:
        raise
    except Exception as error:  # pdfplumber raises several unrelated exception types
        raise _pdf_failure(error) from error

    text_length = sum(len(page) for page in pages)
    return Extracted(pages=pages, kind=FileKind.PDF, needs_ocr=text_length < MIN_USEFUL_CHARS)


def _pdf_failure(error: Exception) -> Exception:
    """Turn a pdfplumber failure into the right application error."""
    message = str(error).casefold()
    if "password" in message or "encrypt" in message:
        return EncryptedDocumentError(
            "This PDF is password-protected. Remove the password and upload it again, "
            "or paste the text instead."
        )
    return InvalidDocumentError(
        "This PDF could not be read. Try saving it again, or paste the text instead."
    )


def _extract_docx(data: bytes) -> Extracted:
    """Read a Word document's paragraphs and tables in order."""
    try:
        document = DocxDocument(io.BytesIO(data))
        lines = [paragraph.text for paragraph in document.paragraphs]
        lines.extend(
            " | ".join(cell.text.strip() for cell in row.cells)
            for table in document.tables
            for row in table.rows
        )
    except Exception as error:  # python-docx raises several unrelated exception types
        raise InvalidDocumentError(
            "This Word file could not be read. Try saving it as a PDF, or paste the text."
        ) from error

    text = "\n".join(line for line in lines if line.strip())
    return Extracted(pages=[text], kind=FileKind.DOCX, needs_ocr=len(text) < MIN_USEFUL_CHARS)


def _extract_text(data: bytes) -> Extracted:
    """Read a plain text file."""
    text = data.decode("utf-8", errors="replace")
    return Extracted(pages=[text], kind=FileKind.TEXT, needs_ocr=False)
