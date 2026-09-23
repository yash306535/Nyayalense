"""Shared constants.

Values that appear in more than one module live here so that no magic number or
magic string is repeated across the codebase.
"""

from typing import Final

APP_NAME: Final = "NyayaLens"
APP_TAGLINE: Final = "Understand what you sign, with proof."
API_PREFIX: Final = "/api/v1"

#: Version of the prompt contract in ``app/prompts/``. Bump on any wording change;
#: it is part of the cache key so stale results are never reused.
PROMPT_VERSION: Final = "2026-09-23.2"

#: Date on which the criminal-law codes of 2023 came into force.
NEW_CODES_IN_FORCE_ON: Final = "2024-07-01"

#: Clause ids are ``C1``, ``C2``, ... and split parts get a letter suffix (``C14a``).
CLAUSE_ID_PREFIX: Final = "C"

#: Characters above which a paragraph is split at a sentence boundary.
MAX_CLAUSE_CHARS: Final = 1200

#: Longest quote a model may return, in words. Longer quotes are rejected outright.
MAX_QUOTE_WORDS: Final = 40

#: Request header carrying the correlation id added by the middleware.
REQUEST_ID_HEADER: Final = "X-Request-ID"

SUPPORTED_LANGUAGES: Final = ("en", "hi", "mr")
