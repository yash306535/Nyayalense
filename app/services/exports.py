"""Producing Word and PDF files.

Rendering is CPU-bound and can be slow, so it runs off the event loop under a
timeout. Files are built in memory and streamed: nothing is written to disk.
"""

import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Final

import anyio

from app.config import Settings
from app.domain.document_model import DocumentModel
from app.domain.enums import ExportFormat
from app.errors import ExportError
from app.rendering import docx, pdf

logger = logging.getLogger(__name__)

MEDIA_TYPES: Final[dict[ExportFormat, str]] = {
    ExportFormat.DOCX: ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ExportFormat.PDF: "application/pdf",
}

#: Filenames end up in a header and on a filesystem, so they are rebuilt from
#: scratch rather than sanitised: only these characters survive.
_SLUG_RE: Final = re.compile(r"[^a-z0-9]+")
MAX_SLUG_CHARS: Final = 60


@dataclass(frozen=True, slots=True)
class ExportedFile:
    """A rendered file, ready to stream."""

    content: bytes
    filename: str
    media_type: str

    @property
    def disposition(self) -> str:
        """The ``Content-Disposition`` header value."""
        return f'attachment; filename="{self.filename}"'


def safe_filename(base: str, extension: str, *, today: datetime | None = None) -> str:
    """Build a download filename that cannot escape its directory.

    Args:
        base: A human-readable name, such as a letter title.
        extension: File extension without the dot.
        today: Date to stamp. Defaults to now, in UTC.

    Returns:
        A name such as ``deposit-refund-request-2026-09-22.docx``.
    """
    slug = _SLUG_RE.sub("-", base.casefold()).strip("-")[:MAX_SLUG_CHARS] or "nyayalens"
    stamp = (today or datetime.now(UTC)).strftime("%Y-%m-%d")
    return f"{slug}-{stamp}.{extension}"


async def export(
    document: DocumentModel, *, export_format: ExportFormat, settings: Settings
) -> ExportedFile:
    """Render a document model to a file.

    Args:
        document: What to render.
        export_format: Word or PDF.
        settings: Resolved settings, supplying the timeout and the PDF variant.

    Returns:
        The rendered file.

    Raises:
        ExportError: Rendering failed or took too long.
    """
    started = anyio.current_time()
    try:
        with anyio.fail_after(settings.export_timeout_seconds):
            content = await anyio.to_thread.run_sync(
                _render, document, export_format, settings.pdf_variant
            )
    except TimeoutError as error:
        logger.warning("export_timeout", extra={"format": export_format.value})
        msg = "Creating the file took too long. Try again, or try the other format."
        raise ExportError(msg) from error

    logger.info(
        "export_done",
        extra={
            "format": export_format.value,
            "bytes": len(content),
            "ms": round((anyio.current_time() - started) * 1000, 1),
        },
    )
    return ExportedFile(
        content=content,
        filename=safe_filename(document.title, export_format.value),
        media_type=MEDIA_TYPES[export_format],
    )


def _render(document: DocumentModel, export_format: ExportFormat, variant: str) -> bytes:
    """Render synchronously, on a worker thread."""
    if export_format is ExportFormat.DOCX:
        return docx.render(document)
    return pdf.render(document, variant=variant)


async def warm_up(settings: Settings) -> None:
    """Render a throwaway PDF so the first real export is not the slow one.

    WeasyPrint loads its font configuration on first use, which can take a few
    seconds. Doing that at startup rather than in front of a waiting user is
    worth a moment of boot time.

    Args:
        settings: Resolved settings.
    """
    from app.domain.document_model import DocumentModel as Model  # noqa: PLC0415
    from app.domain.document_model import paragraph  # noqa: PLC0415

    try:
        await export(
            Model(title="warm-up", blocks=[paragraph("Warming the renderer.")]),
            export_format=ExportFormat.PDF,
            settings=settings,
        )
    except ExportError:
        logger.warning("export_warmup_failed")
