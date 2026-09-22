"""Translate application exceptions into RFC 9457 problem details."""

import logging
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Final

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.constants import REQUEST_ID_HEADER
from app.errors import NyayaLensError

logger = logging.getLogger(__name__)

PROBLEM_MEDIA_TYPE: Final = "application/problem+json"

#: Problem ``type`` URIs are stable identifiers, not fetchable documents.
PROBLEM_TYPE_BASE: Final = "https://nyayalens.example/problems/"

_GENERIC_TITLES: Final = {
    HTTPStatus.BAD_REQUEST: "Bad request",
    HTTPStatus.NOT_FOUND: "Not found",
    HTTPStatus.METHOD_NOT_ALLOWED: "Method not allowed",
    HTTPStatus.REQUEST_ENTITY_TOO_LARGE: "This document is too large",
    HTTPStatus.TOO_MANY_REQUESTS: "Too many requests",
}


def problem_response(
    *,
    status: int,
    code: str,
    title: str,
    detail: str,
    request: Request,
    extra: dict[str, object] | None = None,
) -> JSONResponse:
    """Build a ``application/problem+json`` response.

    Args:
        status: HTTP status code.
        code: Stable slug appended to :data:`PROBLEM_TYPE_BASE`.
        title: Short, user-safe summary.
        detail: User-safe explanation of this occurrence.
        request: The request being answered, used for ``instance`` and the id.
        extra: Additional members to merge into the problem object.

    Returns:
        A JSON response with the problem media type.
    """
    body: dict[str, object] = {
        "type": f"{PROBLEM_TYPE_BASE}{code}",
        "title": title,
        "status": status,
        "detail": detail,
        "instance": request.url.path,
    }
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    if extra:
        body.update(extra)
    return JSONResponse(body, status_code=status, media_type=PROBLEM_MEDIA_TYPE)


async def _handle_unexpected_error(request: Request, exc: Exception) -> Response:
    """Answer an unhandled exception without leaking internals."""
    logger.exception("unhandled_error", exc_info=exc)
    return problem_response(
        status=int(HTTPStatus.INTERNAL_SERVER_ERROR),
        code="internal-error",
        title="Something went wrong",
        detail="NyayaLens could not complete that request. Please try again.",
        request=request,
    )


async def _handle_application_error(request: Request, exc: Exception) -> Response:
    """Answer a deliberate application failure.

    The type check is a real branch rather than an assert: assertions are
    stripped under ``python -O``, and a handler that then leaked an exception
    would turn a tidy 4xx into a stack trace.
    """
    if not isinstance(exc, NyayaLensError):  # pragma: no cover - registered per type
        return await _handle_unexpected_error(request, exc)
    if exc.status >= HTTPStatus.INTERNAL_SERVER_ERROR:
        logger.error("application_error", extra={"code": exc.code}, exc_info=exc)
    else:
        logger.info("application_error", extra={"code": exc.code})
    return problem_response(
        status=int(exc.status),
        code=exc.code,
        title=exc.title,
        detail=exc.detail,
        request=request,
    )


async def _handle_validation_error(request: Request, exc: Exception) -> Response:
    """Answer a request that failed schema validation.

    Field locations and messages are returned, but submitted values are not, so
    no document text or personal data is echoed back.
    """
    if not isinstance(exc, RequestValidationError):  # pragma: no cover - registered per type
        return await _handle_unexpected_error(request, exc)
    errors = [
        {"field": ".".join(str(part) for part in error["loc"][1:]), "message": error["msg"]}
        for error in exc.errors()
    ]
    return problem_response(
        status=int(HTTPStatus.UNPROCESSABLE_ENTITY),
        code="request-invalid",
        title="Some details need fixing",
        detail="Check the fields listed below and try again.",
        request=request,
        extra={"errors": errors},
    )


async def _handle_http_exception(request: Request, exc: Exception) -> Response:
    """Answer a Starlette ``HTTPException`` in problem+json."""
    if not isinstance(exc, HTTPException):  # pragma: no cover - registered per type
        return await _handle_unexpected_error(request, exc)
    status = HTTPStatus(exc.status_code)
    return problem_response(
        status=exc.status_code,
        code=status.phrase.lower().replace(" ", "-"),
        title=_GENERIC_TITLES.get(status, status.phrase),
        detail=str(exc.detail),
        request=request,
    )


Handler = Callable[[Request, Exception], Awaitable[Response]]


def register_error_handlers(app: FastAPI) -> None:
    """Install every problem-details handler on the application.

    Args:
        app: The FastAPI application being built.
    """
    handlers: list[tuple[type[Exception] | int, Handler]] = [
        (NyayaLensError, _handle_application_error),
        (RequestValidationError, _handle_validation_error),
        (HTTPException, _handle_http_exception),
        (Exception, _handle_unexpected_error),
    ]
    for exception, handler in handlers:
        app.add_exception_handler(exception, handler)


__all__ = ["PROBLEM_MEDIA_TYPE", "REQUEST_ID_HEADER", "problem_response", "register_error_handlers"]
