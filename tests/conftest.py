"""Shared fixtures.

Tests never touch the network: the language model is always the deterministic
fake, and every packaged data file is read from the repository.
"""

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from app.adapters.cache import TTLResultCache
from app.adapters.llm.fake import FakeLLMClient
from app.config import Settings
from app.domain.audience import Audience
from app.domain.enums import DocType, Language, ReadingLevel, Role
from app.domain.models import Citation, Clause, Document, Statement
from app.main import create_app
from app.services.context import AnalysisContext
from app.services.ingestion import ingest_text
from app.services.registry import load_registry
from httpx import ASGITransport, AsyncClient

SAMPLES = Path(__file__).resolve().parents[1] / "app" / "data" / "samples"


@pytest.fixture(scope="session")
def settings() -> Settings:
    """Settings for a fully offline run."""
    return Settings(llm_provider="fake", _env_file=None)  # type: ignore[call-arg]


@pytest.fixture(scope="session")
def registry():
    """The packaged data files, loaded once per session."""
    return load_registry()


@pytest.fixture
def context(settings: Settings, registry) -> AnalysisContext:
    """A service context wired to the fake provider and a fresh cache."""
    return AnalysisContext(
        client=FakeLLMClient(),
        settings=settings,
        cache=TTLResultCache(max_items=32, ttl_seconds=60),
        registry=registry,
    )


@pytest.fixture
def audience() -> Audience:
    """A tenant reading English at the simple level."""
    return Audience(role=Role.TENANT, language=Language.EN, reading_level=ReadingLevel.SIMPLE)


def sample_text(name: str) -> str:
    """Read one built-in sample by file stem."""
    return (SAMPLES / f"{name}.txt").read_text(encoding="utf-8")


@pytest.fixture
def rental_document(settings: Settings) -> Document:
    """The rental sample, ingested."""
    return ingest_text(sample_text("leave-licence-v1"), settings=settings).document


@pytest.fixture
def rental_document_v2(settings: Settings) -> Document:
    """The revised rental sample, ingested."""
    return ingest_text(sample_text("leave-licence-v2"), settings=settings).document


@pytest.fixture
def notice_document(settings: Settings) -> Document:
    """The legal-notice sample, which cites sections of three old codes."""
    return ingest_text(sample_text("legal-notice-old-sections"), settings=settings).document


@pytest.fixture
def offer_document(settings: Settings) -> Document:
    """The offer-letter sample, which contains a line addressed to AI systems."""
    return ingest_text(sample_text("offer-letter-bond"), settings=settings).document


@pytest.fixture
def tiny_document() -> Document:
    """A two-clause document, for tests that need exact control of the text."""
    return Document(
        id="test0001",
        doc_type=DocType.RENTAL_LEAVE_LICENCE,
        clauses=[
            Clause(
                id="C1",
                label="4.1",
                heading="Security deposit",
                text=(
                    "The Licensee shall pay a security deposit of Rs. 60,000/- "
                    "(Rupees Sixty Thousand only)."
                ),
                page=1,
            ),
            Clause(
                id="C2",
                label="9",
                heading="Termination",
                text="Either party may terminate this agreement on 30 days written notice.",
                page=2,
            ),
        ],
    )


def statement(text: str, clause_id: str, quote: str) -> Statement:
    """Build an unverified statement, as a model would return it."""
    return Statement(text=text, citations=[Citation(clause_id=clause_id, quote=quote)])


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """An HTTP client bound to the application, in demo mode."""
    app = create_app(Settings(llm_provider="fake", _env_file=None))  # type: ignore[call-arg]
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            yield http
