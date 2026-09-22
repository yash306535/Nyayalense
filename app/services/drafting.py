"""Rendering a letter from facts the user confirmed.

Three rules hold this together. The template is the only source of structure:
user input is data passed into it, never template source. Every interpolated
value is Markdown-escaped, so a fact containing ``**`` or ``#`` prints as
written. And a model may only supply wording that refers to facts through slot
tokens, which code then fills.
"""

import json
import logging
import re
from functools import lru_cache
from typing import Final

from jinja2 import StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

from app.adapters.llm.base import Task
from app.adapters.llm.schemas import LLMWording
from app.config import TEMPLATES_DIR
from app.domain.audience import Audience
from app.domain.document_model import DocumentModel
from app.domain.drafting import slots
from app.domain.drafting.fact_audit import audit
from app.domain.drafting.facts import ConfirmedFacts, DraftTemplate, validate_facts
from app.domain.enums import DocType, Language
from app.domain.models import Document
from app.domain.results import Overview
from app.errors import DataFileError, FactAuditError, NotFoundError
from app.prompts.builder import build
from app.rendering.markdown import parse
from app.services.context import AnalysisContext

logger = logging.getLogger(__name__)

DRAFTS_DIR: Final = TEMPLATES_DIR / "drafts"
TEMPLATE_FILE: Final = "template.md.j2"
FIELDS_FILE: Final = "fields.json"

#: Longest wording a model may suggest for one field.
MAX_WORDING_WORDS: Final = 90

#: Characters that would turn an interpolated fact into Markdown structure.
_MARKDOWN_SPECIALS: Final = re.compile(r"([\\`*_{}\[\]()#+\-.!|>~])")


def escape_markdown(value: object) -> str:
    """Escape a value so it can never become Markdown structure.

    Jinja calls this on every interpolation, so a fact such as ``**urgent**`` or
    ``# Notice`` appears in the letter exactly as the user typed it.

    Args:
        value: The value being interpolated.

    Returns:
        The escaped text. ``None`` becomes an empty string.
    """
    if value is None:
        return ""
    return _MARKDOWN_SPECIALS.sub(r"\\\1", str(value))


@lru_cache(maxsize=1)
def _environment() -> SandboxedEnvironment:
    """Build the sandboxed Jinja environment, once.

    The sandbox blocks attribute access that could reach the interpreter, and
    ``StrictUndefined`` turns a missing fact into an error rather than a silent
    blank in a letter someone is about to send.
    """
    environment = SandboxedEnvironment(
        undefined=StrictUndefined,
        finalize=escape_markdown,
        autoescape=False,
        keep_trailing_newline=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )
    environment.globals.clear()
    return environment


@lru_cache(maxsize=1)
def load_templates() -> dict[str, DraftTemplate]:
    """Load and validate every letter template, once per process.

    Returns:
        Templates keyed by id.

    Raises:
        DataFileError: A template is malformed or missing its body.
    """
    templates: dict[str, DraftTemplate] = {}
    for directory in sorted(path for path in DRAFTS_DIR.iterdir() if path.is_dir()):
        fields_path = directory / FIELDS_FILE
        body_path = directory / TEMPLATE_FILE
        if not fields_path.exists() or not body_path.exists():
            raise DataFileError(f"Template '{directory.name}' is missing a file.")
        try:
            template = DraftTemplate.model_validate(
                json.loads(fields_path.read_text(encoding="utf-8"))
            )
        except ValueError as error:
            raise DataFileError(f"Template '{directory.name}' is invalid.") from error
        templates[template.id] = template

    if not templates:
        raise DataFileError("No letter templates are packaged.")
    return templates


def get_template(template_id: str) -> DraftTemplate:
    """Return one template.

    Raises:
        NotFoundError: There is no template with that id.
    """
    template = load_templates().get(template_id)
    if template is None:
        raise NotFoundError("That letter template does not exist.")
    return template


def _body(template_id: str) -> str:
    """Read a template's Markdown body."""
    return (DRAFTS_DIR / template_id / TEMPLATE_FILE).read_text(encoding="utf-8")


def templates_for(doc_type: DocType | None) -> list[DraftTemplate]:
    """List the templates suited to a document type.

    Args:
        doc_type: The open document's type, or ``None`` for all templates.

    Returns:
        The matching templates, or all of them when nothing matches.
    """
    everything = list(load_templates().values())
    if doc_type is None:
        return everything
    matching = [t for t in everything if doc_type.value in t.doc_types]
    return matching or everything


def render_markdown(template: DraftTemplate, facts: ConfirmedFacts) -> str:
    """Render a template with the confirmed facts.

    Args:
        template: The template to render.
        facts: The user's confirmed facts.

    Returns:
        The rendered Markdown.
    """
    values = {field.name: facts.get(field.name) for field in template.fields}
    return _environment().from_string(_body(template.id)).render(**values)


def build_document(
    template: DraftTemplate, facts: ConfirmedFacts, *, language: Language
) -> DocumentModel:
    """Render a template into the shared document model.

    Args:
        template: The template to render.
        facts: The user's confirmed facts.
        language: Language for the exported file's metadata.

    Returns:
        The document model, with the user's own values marked.

    Raises:
        FactAuditError: A figure appears that is not among the confirmed facts.
    """
    markdown = render_markdown(template, facts)
    supplied = {value.strip() for value in facts.values.values() if value.strip()}
    document = parse(markdown, title=template.title, language=language.value, facts=supplied)

    result = audit(document, confirmed=facts.values, template_constants=_body(template.id))
    if not result.ok:
        logger.warning("fact_audit_failed", extra={"template": template.id})
        raise FactAuditError(result.describe())
    return document


def field_errors(template: DraftTemplate, facts: ConfirmedFacts) -> dict[str, str]:
    """Validate a facts sheet.

    Args:
        template: The template being filled.
        facts: What the user entered.

    Returns:
        Error messages keyed by field name.
    """
    return validate_facts(template, facts)


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
    from app.domain.models import Clause  # noqa: PLC0415 - only needed here

    return Document(
        id=f"wording-{template.id}",
        doc_type=DocType.GENERAL_CONTRACT,
        clauses=[Clause(id="C1", heading=template.title, text=draft or template.title)],
    )


def prefill(
    document: Document, overview: Overview | None
) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """Fill what can be filled from results that are already verified.

    Prefill is deterministic: a value only appears when a verified result
    contains it, and it always arrives with the clause it came from, so the user
    can check it before confirming.

    Args:
        document: The open document.
        overview: The overview result, if one has been produced.

    Returns:
        Values keyed by field name, and the citation behind each.
    """
    values: dict[str, str] = {}
    sources: dict[str, dict[str, str]] = {}
    if overview is None:
        return (values, sources)

    clauses = {clause.id: clause for clause in document.clauses}

    for term in overview.key_terms:
        if not term.value:
            continue
        citation = next(
            (c for statement in term.statements for c in statement.citations if c.verified), None
        )
        values[f"key_term.{term.id}"] = term.value
        if citation is not None:
            clause = clauses.get(citation.clause_id)
            sources[f"key_term.{term.id}"] = {
                "label": clause.label if clause else citation.clause_id,
                "page": str(clause.page) if clause else "",
            }

    other = next((party for party in overview.parties if not party.is_user), None)
    if other is not None:
        values["party.other"] = other.name

    return (values, sources)


def map_prefill(template: DraftTemplate, available: dict[str, str]) -> dict[str, str]:
    """Match prefill values to the fields that asked for them.

    Args:
        template: The template being filled.
        available: Values keyed by their ``prefill_from`` path.

    Returns:
        Values keyed by field name.
    """
    return {
        field.name: available[field.prefill_from]
        for field in template.fields
        if field.prefill_from and field.prefill_from in available
    }
