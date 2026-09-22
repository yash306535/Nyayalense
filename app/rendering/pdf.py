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


def no_network_fetcher(url: str, **_: Any) -> dict[str, Any]:
    """Refuse every fetch.

    An exported document needs nothing from outside: the stylesheet is read from
    disk by path and there are no images. So the safest fetcher is one that
    serves nothing at all. A document can contain text a user or a model
    supplied, and a renderer that will fetch a URL out of that text is a
    server-side request forgery waiting to happen.

    Args:
        url: The URL the renderer wants to fetch.

    Raises:
        ExportError: Always.
    """
    logger.warning("pdf_fetch_refused", extra={"scheme": urlparse(url).scheme.lower()})
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
