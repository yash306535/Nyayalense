"""What-if scenarios.

The question is always "what does this document say about that situation", never
"what would happen". Consequences are only reported when the document states
them, and next steps are practical rather than legal.
"""

import logging

from app.adapters.cache import cache_key
from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMScenario
from app.domain.audience import Audience
from app.domain.models import Document
from app.domain.results import ScenarioResult
from app.domain.verification import ClauseIndex, merge_reports
from app.prompts.builder import build
from app.services.context import AnalysisContext
from app.services.grounding import ground

logger = logging.getLogger(__name__)

NOT_COVERED = "This document does not describe that situation."


async def run_scenario(
    document: Document, scenario: str, *, audience: Audience, context: AnalysisContext
) -> ScenarioResult:
    """Work through one what-if against the document.

    Args:
        document: The document under analysis.
        scenario: The situation the reader asked about.
        audience: The reader's role, language and reading level.
        context: The model adapter, settings, cache and packaged data.

    Returns:
        The result, with every surviving statement verified.
    """
    key = cache_key(
        document_hash=document.id,
        operation=Task.SCENARIO.value,
        model=context.model,
        params={**audience.as_params(), "scenario": scenario},
    )
    cached = context.cache.get(key)
    if isinstance(cached, ScenarioResult):
        return cached

    prompt = build(
        document,
        Task.SCENARIO,
        audience,
        substitutions={"scenario": scenario},
        question=scenario,
    )
    raw = (await context.client.generate(prompt, LLMScenario, task=Task.SCENARIO)).data

    index = ClauseIndex(document)
    says, says_report = ground(raw.says, index, threshold=context.threshold)
    consequences, consequence_report = ground(raw.consequences, index, threshold=context.threshold)

    result = ScenarioResult(
        scenario=scenario,
        says=says,
        consequences=consequences,
        not_covered=raw.not_covered or ([] if says else [NOT_COVERED]),
        next_steps=raw.next_steps,
        verification=merge_reports([says_report, consequence_report]),
    )
    context.cache.set(key, result)
    logger.info(
        "scenario_done",
        extra={"verified": result.verification.verified, "total": result.verification.total},
    )
    return result
