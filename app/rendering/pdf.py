"""Render a document model as a PDF.

WeasyPrint shapes text through Pango and HarfBuzz, so Devanagari renders
correctly, and it can request a tagged PDF. It is also a component that will
fetch any URL it is given, so it is given a fetcher that refuses every network
address and serves only the stylesheet packaged with the application.
"""

import logging
from typing import Any, Final
from urllib.parse import urlparse

from weasyprint import CSS, HTML

from app.config import TEMPLATES_DIR
from app.domain.document_model import DocumentModel
from app.errors import ExportError
from app.rendering.html import render as render_html

logger = logging.getLogger(__name__)

PRINT_CSS: Final = TEMPLATES_DIR / "print.css"

#: The only resources a rendered document may load. Everything else, including
#: every http and https URL, is refused: a document can contain user text, and
#: a renderer that fetches URLs from user text is a server-side request forgery.
_ALLOWED_SCHEMES: Final[frozenset[str]] = frozenset({"data"})


def no_network_fetcher(url: str, **_: Any) -> dict[str, Any]:
    """Serve only packaged resources, refusing every network URL.

    Args:
        url: The URL the renderer wants to fetch.

    Returns:
        A WeasyPrint resource dictionary for an allowed URL.

    Raises:
        ExportError: The URL is not one of the few that are allowed.
    """
    scheme = urlparse(url).scheme.lower()
    if scheme in _ALLOWED_SCHEMES:
        from weasyprint.urls import default_url_fetcher  # noqa: PLC0415 - only on this path

        resource: dict[str, Any] = default_url_fetcher(url)
        return resource

    logger.warning("pdf_fetch_refused", extra={"scheme": scheme})
    msg = "This document tried to load an external resource, so it was not created."
    raise ExportError(msg)


def render(document: DocumentModel, *, variant: str = "pdf/ua-1") -> bytes:
    """Render the document model as a PDF.

    Args:
        document: The document model.
        variant: The PDF variant to request, such as ``pdf/ua-1`` for a tagged,
            accessible PDF. WeasyPrint's support for this is experimental, so
            the output is validated before conformance is claimed anywhere.

    Returns:
        The file's bytes.

    Raises:
        ExportError: Rendering failed.
    """
    html = HTML(string=render_html(document, inline_css=False), url_fetcher=no_network_fetcher)
    stylesheet = CSS(filename=str(PRINT_CSS), url_fetcher=no_network_fetcher)

    try:
        rendered: bytes = html.write_pdf(
            stylesheets=[stylesheet],
            pdf_variant=variant or None,
            uncompressed_pdf=False,
        )
    except ExportError:
        raise
    except Exception as error:  # WeasyPrint raises several unrelated exception types
        logger.exception("pdf_render_failed")
        msg = "The PDF could not be created. Try the Word file instead."
        raise ExportError(msg) from error
    return rendered
