"""Application factory.

Builds the FastAPI app: settings, logging, middleware, error handling, routers
and the static frontend. Packaged data files are validated here, at startup, so
a bad data file stops the process rather than reaching a user.
"""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Final

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.requests import Request
from starlette.responses import Response

from app import __version__
from app.api.deps import get_registry
from app.api.errors import problem_response, register_error_handlers
from app.api.middleware import register_middleware
from app.api.routes import (
    analysis,
    cache,
    calendar,
    checklists,
    compare,
    documents,
    drafts,
    exports,
    glossary,
    health,
    laws,
    meta,
    qa,
    resources,
    scenarios,
)
from app.config import FRONTEND_DIR, Settings, get_settings
from app.constants import API_PREFIX, APP_NAME, APP_TAGLINE
from app.logging_config import configure_logging
from app.services.drafting import load_templates
from app.services.exports import warm_up

logger = logging.getLogger(__name__)

DESCRIPTION: Final = """
NyayaLens explains legal documents that people provide. It is not legal advice.

Every statement in a result carries a quote that code has matched against the document.
Statements that cannot be matched are removed and the removal is reported in
`verification`. When a document does not answer a question, the answer is `not_found`,
never a guess.

Errors are returned as `application/problem+json` (RFC 9457).
""".strip()

TAGS: Final = [
    {"name": "documents", "description": "Reading a document and finding what needs no model."},
    {"name": "analysis", "description": "Explaining and reviewing a whole document."},
    {"name": "ask", "description": "Questions answered only from the document."},
    {"name": "laws", "description": "Mapping old criminal-law sections to the new codes."},
    {"name": "drafting", "description": "Letters from confirmed facts, and Word or PDF files."},
    {"name": "reference data", "description": "Checklists, glossary and the help directory."},
    {"name": "meta", "description": "Build metadata, health and cache control."},
]

_ROUTERS: Final = (
    documents.router,
    analysis.router,
    qa.router,
    compare.router,
    scenarios.router,
    laws.router,
    drafts.router,
    exports.router,
    calendar.router,
    checklists.router,
    glossary.router,
    resources.router,
    cache.router,
    meta.router,
)

#: Cache static assets for a day. They are versioned by the deployment, and the
#: browser revalidates with the ETag Starlette sets.
STATIC_CACHE_SECONDS: Final = 86_400


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Validate packaged data at startup and log what was loaded."""
    get_registry()
    load_templates()
    settings = app.dependency_overrides.get(get_settings, get_settings)()
    if settings.export_warmup:
        await warm_up(settings)
    logger.info("started", extra={"version": __version__})
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the application.

    Args:
        settings: Settings to use. Defaults to the process-wide settings, which
            are read from the environment.

    Returns:
        The configured FastAPI application.
    """
    settings = settings or get_settings()
    configure_logging(settings.log_level)

    app = FastAPI(
        title=APP_NAME,
        summary=APP_TAGLINE,
        description=DESCRIPTION,
        version=__version__,
        openapi_tags=TAGS,
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url=None,
    )

    # Without this, settings passed in would be ignored: every route resolves
    # them through the dependency, which otherwise reads the environment.
    app.dependency_overrides[get_settings] = lambda: settings

    register_middleware(app, settings)
    register_error_handlers(app)
    _register_rate_limiting(app, settings)

    for router in _ROUTERS:
        app.include_router(router, prefix=API_PREFIX)
    app.include_router(health.router)

    _mount_frontend(app)
    return app


def _register_rate_limiting(app: FastAPI, settings: Settings) -> None:
    """Install per-IP rate limiting.

    Behind Cloud Run the client address arrives in ``X-Forwarded-For``, so
    uvicorn must run with ``--proxy-headers`` for this to see the real caller.
    """
    limiter = Limiter(
        key_func=get_remote_address,
        default_limits=[f"{settings.rate_limit_per_minute}/minute"],
        headers_enabled=True,
    )
    app.state.limiter = limiter

    async def _on_rate_limit(request: Request, exc: Exception) -> Response:
        """Answer a throttled request in problem+json."""
        del exc
        return problem_response(
            status=429,
            code="rate-limited",
            title="Too many requests",
            detail="You have made a lot of requests. Wait a minute and try again.",
            request=request,
        )

    app.add_exception_handler(RateLimitExceeded, _on_rate_limit)


def _mount_frontend(app: FastAPI) -> None:
    """Serve the browser application from the same origin.

    Same-origin means no CORS, which keeps the security headers simple and the
    Content-Security-Policy strict.
    """
    if not FRONTEND_DIR.is_dir():  # pragma: no cover - only in a partial checkout
        logger.warning("frontend_missing", extra={"path": str(FRONTEND_DIR)})
        return

    @app.get("/", include_in_schema=False)
    async def index() -> FileResponse:
        """Serve the single page."""
        return FileResponse(FRONTEND_DIR / "index.html")

    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")


app = create_app()
