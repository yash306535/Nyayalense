"""Build metadata and enabled features, for the browser and for operators."""

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app import __version__
from app.api.deps import SettingsDep
from app.constants import APP_NAME, APP_TAGLINE, PROMPT_VERSION, SUPPORTED_LANGUAGES

router = APIRouter(tags=["meta"])


class Meta(BaseModel):
    """What the client needs to know about this deployment.

    Contains no secrets: model ids and flags only, never keys or project ids.
    """

    name: str = Field(description="Product name.")
    tagline: str = Field(description="One-line description.")
    version: str = Field(description="Application version.")
    prompt_version: str = Field(description="Version of the prompt contract in use.")
    demo_mode: bool = Field(description="True when answers come from the offline fake provider.")
    features: dict[str, bool] = Field(description="Feature flags the UI reacts to.")
    languages: list[str] = Field(description="Supported UI and explanation languages.")
    limits: dict[str, int] = Field(description="Client-visible input limits.")


@router.get(
    "/meta",
    response_model=Meta,
    summary="Deployment metadata",
    description="Version, prompt version, enabled features and input limits. No secrets.",
)
async def meta(settings: SettingsDep) -> Meta:
    """Describe this deployment to the client."""
    return Meta(
        name=APP_NAME,
        tagline=APP_TAGLINE,
        version=__version__,
        prompt_version=PROMPT_VERSION,
        demo_mode=settings.is_demo_mode,
        features=settings.enabled_features(),
        languages=list(SUPPORTED_LANGUAGES),
        limits={
            "max_upload_mb": settings.max_upload_mb,
            "max_pages": settings.max_pages,
            "max_document_chars": settings.max_document_chars,
            "max_clauses": settings.max_clauses,
        },
    )
