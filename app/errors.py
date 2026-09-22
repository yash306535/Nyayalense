"""Application exception hierarchy.

Every failure the application raises on purpose is one of these. The API layer
translates them to RFC 9457 problem details in :mod:`app.api.errors`; nothing
else needs to know about HTTP.
"""

from http import HTTPStatus


class NyayaLensError(Exception):
    """Base class for every deliberate application failure.

    Attributes:
        code: Stable, URL-safe identifier used as the problem-details ``type``.
        status: HTTP status the API layer should return.
        title: Short, user-safe summary.
    """

    code = "internal-error"
    status = HTTPStatus.INTERNAL_SERVER_ERROR
    title = "Something went wrong"

    def __init__(self, detail: str) -> None:
        """Store a user-safe explanation of the failure.

        Args:
            detail: Message shown to the user. Must never contain document text,
                questions, answers or credentials.
        """
        super().__init__(detail)
        self.detail = detail


class InvalidDocumentError(NyayaLensError):
    """The file was readable but produced nothing usable."""

    code = "invalid-document"
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    title = "This document could not be read"


class UnsupportedFileTypeError(NyayaLensError):
    """The bytes do not match any supported format."""

    code = "unsupported-file-type"
    status = HTTPStatus.UNSUPPORTED_MEDIA_TYPE
    title = "This file type is not supported"


class DocumentTooLargeError(NyayaLensError):
    """The upload exceeded a configured size or page limit."""

    code = "document-too-large"
    status = HTTPStatus.REQUEST_ENTITY_TOO_LARGE
    title = "This document is too large"


class EncryptedDocumentError(NyayaLensError):
    """The PDF is password-protected, so no text can be extracted."""

    code = "encrypted-document"
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    title = "This PDF is password-protected"


class LLMOutputError(NyayaLensError):
    """The model returned something that did not satisfy the schema."""

    code = "model-output-invalid"
    status = HTTPStatus.BAD_GATEWAY
    title = "The analysis could not be completed"


class UpstreamServiceError(NyayaLensError):
    """A dependency failed or timed out."""

    code = "upstream-unavailable"
    status = HTTPStatus.SERVICE_UNAVAILABLE
    title = "A service NyayaLens depends on is unavailable"


class RateLimitedError(NyayaLensError):
    """The caller exceeded its request budget."""

    code = "rate-limited"
    status = HTTPStatus.TOO_MANY_REQUESTS
    title = "Too many requests"


class NotFoundError(NyayaLensError):
    """A requested sample, template, checklist or provision does not exist."""

    code = "not-found"
    status = HTTPStatus.NOT_FOUND
    title = "Not found"


class FactsNotConfirmedError(NyayaLensError):
    """An export was requested before the user confirmed the facts sheet."""

    code = "facts-not-confirmed"
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    title = "Confirm your facts before downloading"


class SlotLockError(NyayaLensError):
    """Model-suggested wording broke the slot contract and was rejected."""

    code = "slot-lock-violation"
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    title = "Suggested wording was rejected"


class FactAuditError(NyayaLensError):
    """A rendered document contained a figure that is not a confirmed fact."""

    code = "fact-audit-failed"
    status = HTTPStatus.UNPROCESSABLE_ENTITY
    title = "This draft contains a figure you did not confirm"


class ExportError(NyayaLensError):
    """Word or PDF rendering failed or timed out."""

    code = "export-failed"
    status = HTTPStatus.INTERNAL_SERVER_ERROR
    title = "The file could not be created"


class DataFileError(NyayaLensError):
    """A packaged data file is missing or does not match its schema.

    Raised at startup, which stops the process rather than serving bad data.
    """

    code = "data-file-invalid"
    status = HTTPStatus.INTERNAL_SERVER_ERROR
    title = "A packaged data file is invalid"
