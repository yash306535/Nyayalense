"""Asking a model to word one field better, without letting it supply a fact.

The model returns wording that refers to facts only through ``[[slot]]`` tokens.
The slot lock rejects anything carrying a figure, a date or a contact detail
outside one, and code then fills the slots from the confirmed facts. So a model
can improve a sentence and still never type a number into a letter.
"""

import logging
from typing import Final

from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMWording
from app.domain.audience import Audience
from app.domain.drafting import slots
from app.domain.drafting.facts import ConfirmedFacts, DraftTemplate
from app.domain.enums import DocType
from app.domain.models import Clause, Document
from app.prompts.builder import build
from app.services.context import AnalysisContext

logger = logging.getLogger(__name__)

#: Longest wording a model may suggest for one field.
MAX_WORDING_WORDS: Final = 90


async def suggest_wording(
    template: DraftTemplate,
    draft: str,
    facts: ConfirmedFacts,
    *,
    audience: Audience,
    context: AnalysisContext,
) -> tuple[str, bool]:
    """Ask the model to word one free-text field better.

    Args:
        template: The template being filled.
        draft: What the user has written so far.
        facts: The confirmed facts, used to fill the slots afterwards.
        audience: The reader's language and reading level.
        context: The model adapter, settings, cache and packaged data.

    Returns:
        The wording to use, and whether the model's suggestion was rejected.
        On rejection the user's own text is returned unchanged and the UI says
        so, because silently substituting different words would be worse than
        offering none.
    """
    field_name = template.wording_field
    if field_name is None or not context.settings.enable_ai_wording:
        return (draft, False)

    field = template.field(field_name)
    label = field.label_in(audience.language) if field else field_name
    allowed = template.slot_names
    required = set(template.required_slots)

    prompt = build(
        _wording_document(template, draft),
        Task.WORDING,
        audience,
        substitutions={
            "slots": ", ".join(f"[[{name}]]" for name in sorted(allowed)),
            "required": ", ".join(f"[[{name}]]" for name in sorted(required)) or "none",
            "max_words": str(MAX_WORDING_WORDS),
            "field_label": label,
            "draft": draft,
        },
    )
    suggestion = (await context.client.generate(prompt, LLMWording, task=Task.WORDING)).data

    outcome = slots.check(
        suggestion.text, allowed=allowed, required=required, max_words=MAX_WORDING_WORDS
    )
    if not outcome.ok:
        logger.info(
            "wording_rejected",
            extra={
                "template": template.id,
                "violation": outcome.violation and outcome.violation.value,
            },
        )
        return (draft, True)

    return (slots.fill(suggestion.text, facts.values), False)


def _wording_document(template: DraftTemplate, draft: str) -> Document:
    """Wrap the draft as a one-clause document so the prompt builder can take it."""
    return Document(
        id=f"wording-{template.id}",
        doc_type=DocType.GENERAL_CONTRACT,
        clauses=[Clause(id="C1", heading=template.title, text=draft or template.title)],
    )
