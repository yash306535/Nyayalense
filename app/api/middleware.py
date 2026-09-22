"""ASGI middleware: request ids, security headers, body limits and timing logs."""

import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from http import HTTPStatus
from typing import Final

from fastapi import FastAPI
from starlette.datastructures import MutableHeaders
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.errors import PROBLEM_MEDIA_TYPE, PROBLEM_TYPE_BASE
from app.config import Settings
from app.constants import REQUEST_ID_HEADER

logger = logging.getLogger(__name__)

CONTENT_SECURITY_POLICY: Final = "; ".join(
    (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "img-src 'self' data:",
        "media-src 'self' blob:",
        "font-src 'self'",
        "connect-src 'self'",
        "object-src 'none'",
        "base-uri 'none'",
        "frame-ancestors 'none'",
        "form-action 'self'",
    )
)

#: Camera and geolocation are never needed. Microphone stays off until the
#: opt-in voice-input feature ships, which will relax this one entry.
PERMISSIONS_POLICY: Final = "camera=(), geolocation=(), microphone=(), payment=(), usb=()"

SECURITY_HEADERS: Final[dict[str, str]] = {
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": PERMISSIONS_POLICY,
    "Cross-Origin-Opener-Policy": "same-origin",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Embedder-Policy": "require-corp",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
}

GZIP_MINIMUM_SIZE: Final = 1024


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Attach a correlation id, add security headers and log timings.

    Logs carry metadata only: method, path, status, duration and the request id.
    Document text, questions, answers and facts are never logged.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        """Wrap one request/response cycle."""
        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        response = await call_next(request)

        duration_ms = round((time.perf_counter() - started) * 1000, 1)
        response.headers[REQUEST_ID_HEADER] = request_id
        for header, value in SECURITY_HEADERS.items():
            response.headers.setdefault(header, value)
        logger.info(
            "request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        return response


class BodySizeLimitMiddleware:
    """Reject oversized request bodies while they stream in.

    Checking ``Content-Length`` alone is not enough: a chunked upload declares no
    length. This counts bytes as they arrive and answers 413 as soon as the limit
    is passed, so an oversized file is never held in memory in full.
    """

    def __init__(self, app: ASGIApp, *, max_bytes: int) -> None:
        """Store the wrapped app and the byte limit.

        Args:
            app: The next ASGI application.
            max_bytes: Largest body accepted, in bytes.
        """
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        """Count body bytes and refuse the request once the limit is passed."""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        if self._declared_length_exceeds_limit(scope):
            await self._send_too_large(scope, send)
            return

        received = 0

        async def counting_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise _BodyTooLargeError
            return message

        try:
            await self.app(scope, counting_receive, send)
        except _BodyTooLargeError:
            await self._send_too_large(scope, send)

    def _declared_length_exceeds_limit(self, scope: Scope) -> bool:
        """Check the ``Content-Length`` header before reading anything."""
        for name, value in scope.get("headers", []):
            if name == b"content-length":
                try:
                    return int(value) > self.max_bytes
                except ValueError:
                    return False
        return False

    async def _send_too_large(self, scope: Scope, send: Send) -> None:
        """Emit a problem+json 413 without invoking the application."""
        megabytes = self.max_bytes // (1024 * 1024)
        body = (
            f'{{"type":"{PROBLEM_TYPE_BASE}document-too-large",'
            f'"title":"This document is too large",'
            f'"status":{int(HTTPStatus.REQUEST_ENTITY_TOO_LARGE)},'
            f'"detail":"Upload a file of {megabytes} MB or less, or paste the text instead.",'
            f'"instance":"{scope.get("path", "")}"}}'
        ).encode()
        headers = MutableHeaders()
        headers["content-type"] = PROBLEM_MEDIA_TYPE
        headers["content-length"] = str(len(body))
        for header, value in SECURITY_HEADERS.items():
            headers[header] = value
        await send(
            {
                "type": "http.response.start",
                "status": int(HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
                "headers": headers.raw,
            }
        )
        await send({"type": "http.response.body", "body": body})


class _BodyTooLargeError(Exception):
    """Internal signal that the streamed body passed the limit."""


def register_middleware(app: FastAPI, settings: Settings) -> None:
    """Install every middleware, outermost first.

    Args:
        app: The FastAPI application being built.
        settings: Resolved settings supplying the upload limit.
    """
    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(GZipMiddleware, minimum_size=GZIP_MINIMUM_SIZE)
    app.add_middleware(BodySizeLimitMiddleware, max_bytes=settings.max_upload_bytes)
