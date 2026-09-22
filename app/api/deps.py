"""Dependency providers.

Adapters are resolved here and nowhere else, so a test can swap any of them by
overriding a single dependency.
"""

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request

from app.adapters.cache import ResultCache, TTLResultCache
from app.adapters.llm.base import LLMClient
from app.config import LLMProvider, Settings, get_settings
from app.constants import REQUEST_ID_HEADER
from app.services.context import AnalysisContext
from app.services.registry import Registry, load_registry

SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_request_id(request: Request) -> str:
    """Return the correlation id the middleware attached to this request."""
    request_id = getattr(request.state, "request_id", "")
    return str(request_id) or request.headers.get(REQUEST_ID_HEADER, "")


RequestIdDep = Annotated[str, Depends(get_request_id)]


def get_llm_client(settings: SettingsDep) -> LLMClient:
    """Resolve the configured language-model adapter.

    The Gemini module is imported only when it is needed, so the application
    starts in demo mode without the Google SDK installed.

    Args:
        settings: Resolved application settings.

    Returns:
        The Gemini adapter, or the deterministic fake used by tests and demos.
    """
    if settings.llm_provider is LLMProvider.FAKE:
        from app.adapters.llm.fake import FakeLLMClient  # noqa: PLC0415 - lazy by design

        return FakeLLMClient()

    from app.adapters.llm.gemini import GeminiLLMClient  # noqa: PLC0415 - lazy by design

    return GeminiLLMClient(settings)


LLMClientDep = Annotated[LLMClient, Depends(get_llm_client)]


@lru_cache(maxsize=1)
def get_registry() -> Registry:
    """Load the packaged data files once per process.

    Returns:
        The validated registry of checklists, glossary, resources, samples and
        law data.
    """
    return load_registry()


RegistryDep = Annotated[Registry, Depends(get_registry)]


@lru_cache(maxsize=1)
def _cache_for(max_items: int, ttl_seconds: int) -> TTLResultCache:
    """Build the process-wide result cache, once per configuration."""
    return TTLResultCache(max_items=max_items, ttl_seconds=ttl_seconds)


def get_cache(settings: SettingsDep) -> ResultCache:
    """Return the shared analysis-result cache."""
    return _cache_for(settings.cache_max_items, settings.cache_ttl_seconds)


CacheDep = Annotated[ResultCache, Depends(get_cache)]


def get_context(
    client: LLMClientDep, settings: SettingsDep, cache: CacheDep, registry: RegistryDep
) -> AnalysisContext:
    """Bundle the collaborators every analysis service needs."""
    return AnalysisContext(client=client, settings=settings, cache=cache, registry=registry)


ContextDep = Annotated[AnalysisContext, Depends(get_context)]
