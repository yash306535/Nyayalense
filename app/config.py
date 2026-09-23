"""Typed application settings.

Every environment variable the application reads is declared here with a type, a
default and a description. Nothing else in the codebase calls ``os.environ``.
"""

from enum import StrEnum
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PACKAGE_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_ROOT.parent
DATA_DIR = PACKAGE_ROOT / "data"
TEMPLATES_DIR = PACKAGE_ROOT / "templates"
PROMPTS_DIR = PACKAGE_ROOT / "prompts"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


class LLMProvider(StrEnum):
    """Which language-model adapter the services resolve to."""

    GEMINI = "gemini"
    FAKE = "fake"


class Settings(BaseSettings):
    """Runtime configuration, read once at startup from the environment."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
    )

    # -------------------------------------------------------------- model provider
    llm_provider: LLMProvider = Field(
        default=LLMProvider.FAKE,
        description="'gemini' for the real API, 'fake' for the offline demo provider.",
    )
    gemini_api_key: str | None = Field(
        default=None, description="AI Studio API key. Unset when using Vertex AI."
    )
    google_genai_use_vertexai: bool = Field(
        default=False, description="Authenticate through Vertex AI with ADC instead of a key."
    )
    google_cloud_project: str | None = Field(default=None, description="Vertex AI project id.")
    google_cloud_location: str = Field(
        default="global",
        description=(
            "Vertex AI location for Gemini calls. Most Gemini models are served "
            "only from the global endpoint, not every regional one."
        ),
    )
    gemini_model: str = Field(
        default="gemini-3.6-flash", description="Main model for analysis and Q&A."
    )
    gemini_model_lite: str = Field(
        default="gemini-3.1-flash-lite", description="Cheap model for document-type fallback."
    )
    gemini_thinking_level: Literal["none", "low", "medium", "high"] = Field(
        default="low", description="Reasoning effort for extraction tasks."
    )

    # -------------------------------------------------------------- optional services
    enable_dlp: bool = Field(
        default=False, description="Use Sensitive Data Protection for masking; regex always runs."
    )
    enable_document_ai: bool = Field(default=False, description="Use Document AI for OCR.")
    document_ai_processor: str | None = Field(
        default=None, description="Full Document AI processor resource name."
    )
    enable_tts: bool = Field(default=False, description="Use Cloud Text-to-Speech for read-aloud.")
    enable_check_grounding: bool = Field(
        default=False, description="Score statements with the Check Grounding API."
    )
    grounding_min_support: Annotated[float, Field(ge=0.0, le=1.0)] = Field(
        default=0.6, description="Statements below this support score are flagged."
    )

    # -------------------------------------------------------------- verification / drafting
    quote_match_threshold: Annotated[int, Field(ge=50, le=100)] = Field(
        default=92, description="Minimum rapidfuzz partial ratio for a quote to verify."
    )
    enable_ai_wording: bool = Field(
        default=True, description="Offer model-suggested wording for free-text letter fields."
    )

    # -------------------------------------------------------------- exports and law data
    pdf_variant: str = Field(default="pdf/ua-1", description="WeasyPrint PDF variant to request.")
    export_timeout_seconds: Annotated[float, Field(gt=0)] = Field(
        default=20.0, description="Hard limit on a single Word or PDF render."
    )
    export_warmup: bool = Field(
        default=False, description="Render a throwaway PDF at startup so the first export is fast."
    )
    law_data_show_unreviewed: bool = Field(
        default=False, description="Show law rows still marked 'extracted' (labelled in the UI)."
    )

    # -------------------------------------------------------------- limits
    max_upload_mb: Annotated[int, Field(ge=1, le=50)] = Field(
        default=10, description="Largest accepted upload."
    )
    max_pages: Annotated[int, Field(ge=1, le=500)] = Field(
        default=60, description="Largest accepted page count."
    )
    max_document_chars: Annotated[int, Field(ge=1000)] = Field(
        default=400_000, description="Largest accepted extracted text length."
    )
    max_clauses: Annotated[int, Field(ge=10)] = Field(
        default=1500, description="Largest accepted clause count in a client-held document."
    )
    rate_limit_per_minute: Annotated[int, Field(ge=1)] = Field(
        default=30, description="Per-IP request budget for analysis endpoints."
    )
    export_rate_limit_per_minute: Annotated[int, Field(ge=1)] = Field(
        default=10, description="Stricter per-IP budget for export endpoints."
    )
    llm_timeout_seconds: Annotated[float, Field(gt=0)] = Field(
        default=60.0, description="Hard limit on a single model call."
    )
    llm_max_concurrency: Annotated[int, Field(ge=1)] = Field(
        default=8, description="Global cap on in-flight model calls."
    )

    # -------------------------------------------------------------- cache and logs
    cache_ttl_seconds: Annotated[int, Field(ge=0)] = Field(
        default=1800, description="Lifetime of a cached analysis result."
    )
    cache_max_items: Annotated[int, Field(ge=1)] = Field(
        default=256, description="Cache capacity; least-recently-used entries are dropped."
    )
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", description="Root log level."
    )

    @field_validator("document_ai_processor")
    @classmethod
    def _processor_looks_like_a_resource_name(cls, value: str | None) -> str | None:
        """Reject a processor id that is not a full resource name.

        An unset ``.env`` line reads as an empty string, not as absent, and an
        empty processor is harmless while ``ENABLE_DOCUMENT_AI`` is off. Only a
        non-empty value gets held to the resource-name shape.
        """
        if not value:
            return None
        if not value.startswith("projects/"):
            msg = "DOCUMENT_AI_PROCESSOR must be a full resource name starting with 'projects/'"
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _credentials_match_the_provider(self) -> "Settings":
        """Fail fast when the Gemini provider has no usable credentials."""
        if self.llm_provider is not LLMProvider.GEMINI:
            return self
        if self.google_genai_use_vertexai:
            if not self.google_cloud_project:
                msg = "GOOGLE_CLOUD_PROJECT is required when GOOGLE_GENAI_USE_VERTEXAI is true"
                raise ValueError(msg)
        elif not self.gemini_api_key:
            msg = "GEMINI_API_KEY is required when LLM_PROVIDER=gemini without Vertex AI"
            raise ValueError(msg)
        return self

    @property
    def max_upload_bytes(self) -> int:
        """Upload limit in bytes."""
        return self.max_upload_mb * 1024 * 1024

    @property
    def is_demo_mode(self) -> bool:
        """True when answers come from the offline fake provider."""
        return self.llm_provider is LLMProvider.FAKE

    def enabled_features(self) -> dict[str, bool]:
        """Feature flags safe to expose to the browser (never secrets)."""
        return {
            "demo_mode": self.is_demo_mode,
            "ai_wording": self.enable_ai_wording and not self.is_demo_mode,
            "dlp": self.enable_dlp,
            "document_ai": self.enable_document_ai,
            "tts": self.enable_tts,
            "check_grounding": self.enable_check_grounding,
            "show_unreviewed_law_rows": self.law_data_show_unreviewed,
        }


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide settings, built once."""
    return Settings()
