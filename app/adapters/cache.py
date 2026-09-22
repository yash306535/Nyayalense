"""A bounded, in-memory result cache.

Analysis is the expensive part of a request and the same document is analysed
repeatedly as the user moves between tabs. Caching by content hash makes that
free. Nothing is written to disk, entries expire, and the cache is capacity-
bound, so a busy instance cannot accumulate documents in memory.
"""

import hashlib
import json
from typing import Any, Final, Protocol

from cachetools import TTLCache

from app.constants import PROMPT_VERSION

HASH_LENGTH: Final = 32


class ResultCache(Protocol):
    """What the services need from a cache."""

    def get(self, key: str) -> Any | None:
        """Return the cached value for ``key``, or ``None``."""
        ...

    def set(self, key: str, value: Any) -> None:
        """Store ``value`` under ``key``."""
        ...

    def purge(self, prefix: str) -> int:
        """Drop every entry whose key starts with ``prefix``.

        Returns:
            How many entries were dropped.
        """
        ...


class TTLResultCache:
    """A time-to-live cache with a hard item limit."""

    def __init__(self, *, max_items: int, ttl_seconds: int) -> None:
        """Build the cache.

        Args:
            max_items: Capacity. The least recently used entry is dropped first.
            ttl_seconds: Lifetime of an entry.
        """
        self._store: TTLCache[str, Any] = TTLCache(maxsize=max_items, ttl=ttl_seconds)

    def get(self, key: str) -> Any | None:
        """Return the cached value for ``key``, or ``None`` when absent or stale."""
        return self._store.get(key)

    def set(self, key: str, value: Any) -> None:
        """Store ``value`` under ``key``."""
        self._store[key] = value

    def purge(self, prefix: str) -> int:
        """Drop every entry whose key starts with ``prefix``."""
        doomed = [key for key in list(self._store) if key.startswith(prefix)]
        for key in doomed:
            self._store.pop(key, None)
        return len(doomed)

    def __len__(self) -> int:
        """How many live entries the cache holds."""
        return len(self._store)


def content_hash(payload: Any) -> str:
    """Hash a JSON-serialisable payload to a short hex digest.

    Args:
        payload: Anything ``json.dumps`` can handle with ``default=str``.

    Returns:
        A truncated SHA-256 digest, stable across processes.
    """
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()[:HASH_LENGTH]


def cache_key(*, document_hash: str, operation: str, model: str, params: Any = None) -> str:
    """Build the cache key for one analysis.

    The prompt version is part of the key, so editing a prompt file can never
    serve a result produced by the previous wording.

    Args:
        document_hash: Identity of the document being analysed.
        operation: Which analysis, for example ``"overview"``.
        model: Model id the result would come from.
        params: Any further inputs, such as role, language or a question.

    Returns:
        A key beginning with ``"<document_hash>:"`` so a document's entries can
        be purged together.
    """
    suffix = content_hash([operation, model, PROMPT_VERSION, params])
    return f"{document_hash}:{suffix}"
