"""Identity for documents and analyses.

The API is stateless: the browser holds the clause map and sends it back with
every request. A document therefore needs a content-derived identity, so that a
cached analysis is reused when and only when the text is genuinely the same.
"""

from app.adapters.cache import content_hash
from app.domain.models import Clause


def document_id(clauses: list[Clause]) -> str:
    """Derive a stable id from a document's own text.

    Args:
        clauses: The clause map, after masking.

    Returns:
        A short hex digest. The same text always produces the same id, on any
        instance, which is what lets Cloud Run scale horizontally.
    """
    return content_hash([[clause.id, clause.label, clause.text] for clause in clauses])
