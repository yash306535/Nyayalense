"""Gemini adapter.

Structured output does most of the work: the response schema comes from the same
Pydantic model the caller expects back, so a malformed response is a parse
error rather than a subtly wrong result. One retry is allowed, with the
validation error appended, and then the call fails loudly.
"""

import asyncio
import logging
import time
from typing import Any, Final

from google import genai
from google.genai import errors as genai_errors
from google.genai import types
from pydantic import ValidationError

from app.adapters.llm.base import LLMResult, LLMUsage, Prompt, ResponseT, Task
from app.config import Settings
from app.errors import LLMOutputError, UpstreamServiceError

logger = logging.getLogger(__name__)

_THINKING_LEVELS: Final[dict[str, types.ThinkingLevel]] = {
    "none": types.ThinkingLevel.MINIMAL,
    "low": types.ThinkingLevel.LOW,
    "medium": types.ThinkingLevel.MEDIUM,
    "high": types.ThinkingLevel.HIGH,
}

#: Tasks cheap enough for the lite model.
_LITE_TASKS: Final[frozenset[Task]] = frozenset({Task.DOC_TYPE})

#: Ceiling on generated tokens. Every schema here is a short structured object,
#: so this is a cost guard rather than a real constraint.
MAX_OUTPUT_TOKENS: Final = 8192

MILLISECONDS: Final = 1000

#: One global semaphore, so a burst of requests cannot fan out into a burst of
#: model calls. Shared across adapter instances because the limit is per process.
_CONCURRENCY: dict[int, asyncio.Semaphore] = {}


def _semaphore(limit: int) -> asyncio.Semaphore:
    """Return the process-wide semaphore for this concurrency limit."""
    if limit not in _CONCURRENCY:
        _CONCURRENCY[limit] = asyncio.Semaphore(limit)
    return _CONCURRENCY[limit]


class GeminiLLMClient:
    """Calls Gemini through the ``google-genai`` SDK, on AI Studio or Vertex AI."""

    def __init__(self, settings: Settings) -> None:
        """Build a client for the configured credentials.

        Args:
            settings: Resolved application settings.
        """
        self._settings = settings
        self._client = self._build_client(settings)

    @staticmethod
    def _build_client(settings: Settings) -> genai.Client:
        """Create the SDK client for the configured authentication mode."""
        http_options = types.HttpOptions(timeout=int(settings.llm_timeout_seconds * MILLISECONDS))
        if settings.google_genai_use_vertexai:
            return genai.Client(
                vertexai=True,
                project=settings.google_cloud_project,
                location=settings.google_cloud_location,
                http_options=http_options,
            )
        return genai.Client(api_key=settings.gemini_api_key, http_options=http_options)

    def _model_for(self, task: Task) -> str:
        """Pick the main or the lite model for a task."""
        return (
            self._settings.gemini_model_lite if task in _LITE_TASKS else self._settings.gemini_model
        )

    def _config(self, prompt: Prompt, schema: type[ResponseT]) -> types.GenerateContentConfig:
        """Build the generation config.

        Sampling parameters are deliberately not set: Google has deprecated them
        for current models, and consistency here comes from the response schema
        and from verification, not from a low temperature.
        """
        return types.GenerateContentConfig(
            system_instruction=prompt.system,
            response_mime_type="application/json",
            response_schema=schema,
            max_output_tokens=MAX_OUTPUT_TOKENS,
            thinking_config=types.ThinkingConfig(
                thinking_level=_THINKING_LEVELS[self._settings.gemini_thinking_level]
            ),
        )

    async def generate(
        self, prompt: Prompt, schema: type[ResponseT], *, task: Task
    ) -> LLMResult[ResponseT]:
        """Run one call, retrying once if the response does not fit the schema.

        Args:
            prompt: The prompt to send.
            schema: Pydantic model describing the required JSON shape.
            task: Which analysis this call performs.

        Returns:
            The parsed response and the call's usage metadata.

        Raises:
            LLMOutputError: The response failed validation twice.
            UpstreamServiceError: The call failed or timed out.
        """
        model = self._model_for(task)
        body = prompt.as_text()
        started = time.perf_counter()

        async with _semaphore(self._settings.llm_max_concurrency):
            response, retried = await self._call_with_one_retry(prompt, schema, model, body)

        data, usage_metadata = response
        elapsed_ms = round((time.perf_counter() - started) * MILLISECONDS, 1)
        usage = _usage(usage_metadata, model=model, latency_ms=elapsed_ms, retried=retried)
        logger.info(
            "llm_call",
            extra={
                "task": task.value,
                "model": model,
                "prompt_tokens": usage.prompt_tokens,
                "output_tokens": usage.output_tokens,
                "cached_tokens": usage.cached_tokens,
                "latency_ms": usage.latency_ms,
                "retried": retried,
            },
        )
        return LLMResult(data=data, usage=usage)

    async def _call_with_one_retry(
        self, prompt: Prompt, schema: type[ResponseT], model: str, body: str
    ) -> tuple[tuple[ResponseT, Any], bool]:
        """Send the prompt, and on a validation failure send it once more."""
        try:
            return (await self._send(prompt, schema, model, body), False)
        except ValidationError as first_error:
            logger.warning("llm_output_invalid", extra={"model": model, "attempt": 1})
            repair = (
                f"{body}\n\nYour previous reply did not match the schema. "
                f"Errors: {first_error.errors(include_url=False, include_input=False)}\n"
                f"Reply again with JSON that matches the schema exactly."
            )
            try:
                return (await self._send(prompt, schema, model, repair), True)
            except ValidationError as second_error:
                raise LLMOutputError(
                    "NyayaLens could not read the analysis it received. Please try again."
                ) from second_error

    async def _send(
        self, prompt: Prompt, schema: type[ResponseT], model: str, body: str
    ) -> tuple[ResponseT, Any]:
        """Send one request and parse the response.

        Raises:
            ValidationError: The response did not satisfy the schema.
            UpstreamServiceError: The call failed, timed out or was refused.
        """
        try:
            response = await self._client.aio.models.generate_content(
                model=model, contents=body, config=self._config(prompt, schema)
            )
        except genai_errors.APIError as error:
            raise UpstreamServiceError(
                "The analysis service is not responding. Please try again in a moment."
            ) from error
        except TimeoutError as error:
            raise UpstreamServiceError(
                "The analysis took too long. Try a shorter document or try again."
            ) from error

        text = response.text
        if not text:
            raise UpstreamServiceError("The analysis service returned an empty response.")
        return (schema.model_validate_json(text), response.usage_metadata)


def _usage(metadata: Any, *, model: str, latency_ms: float, retried: bool) -> LLMUsage:
    """Convert SDK usage metadata into the adapter-neutral record."""
    return LLMUsage(
        prompt_tokens=int(getattr(metadata, "prompt_token_count", 0) or 0),
        output_tokens=int(getattr(metadata, "candidates_token_count", 0) or 0),
        cached_tokens=int(getattr(metadata, "cached_content_token_count", 0) or 0),
        latency_ms=latency_ms,
        model=model,
        retried=retried,
    )


__all__ = ["GeminiLLMClient"]
