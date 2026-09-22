"""The collaborators every analysis service needs.

Bundling them keeps service signatures short and gives a test one object to
substitute instead of four separate arguments.
"""

from dataclasses import dataclass

from app.adapters.cache import ResultCache
from app.adapters.llm.base import LLMClient
from app.config import Settings
from app.services.registry import Registry


@dataclass(frozen=True, slots=True)
class AnalysisContext:
    """Everything a service needs beyond the document itself.

    Attributes:
        client: The configured language-model adapter.
        settings: Resolved application settings.
        cache: Where a previous identical result may be waiting.
        registry: The validated packaged data files.
    """

    client: LLMClient
    settings: Settings
    cache: ResultCache
    registry: Registry

    @property
    def threshold(self) -> int:
        """Minimum partial ratio for a quote to verify."""
        return self.settings.quote_match_threshold

    @property
    def model(self) -> str:
        """Model id that results should be cached against."""
        return "fake" if self.settings.is_demo_mode else self.settings.gemini_model
