# Contributing

## Getting set up

```bash
make install     # Python 3.12 virtualenv, everything pinned
make dev-fake    # http://localhost:8080, offline, no keys needed
```

Optionally `pre-commit install` for the fast checks before each commit.

## Before you push

```bash
make check       # lint, types, security scans, tests. Exactly what CI runs.
make e2e         # Playwright and axe, if you touched the frontend
```

`make check` passing locally means CI passes, because they run the same targets.

## The rules that are not negotiable

These are the product, not house style. A change that weakens one of them needs
a very good reason and an ADR.

1. **Nothing reaches the reader unverified.** Model output is a DTO in
   `app/adapters/llm/schemas.py`. Only `app/domain/verification.py` may set
   `verified`, a score or a span. The single crossing point is
   `app/services/grounding.py`. If you find yourself adding a second, stop.
2. **"This document doesn't say" is a result.** Never fill a gap with what such
   documents usually contain.
3. **No legal advice.** Never "sign / don't sign", never predict an outcome,
   never state what the law requires. `evals/dataset.json` tests these refusals.
4. **Law data and help contacts come from official sources**, each row carrying
   its source and review date. Never write one from memory. See `docs/DATA.md`.
5. **Drafts contain only confirmed facts.** A model may suggest wording, and
   refers to facts only through `[[slot]]` tokens that code fills in.
6. **Never `innerHTML` with dynamic data.** Build DOM with `frontend/js/dom.js`.
7. **No inline scripts or styles.** The Content-Security-Policy has no
   exceptions and is not going to get one.
8. **Nothing fabricated in the docs.** If a number is not measured, do not
   publish it. If something was not run, say so.

## Conventions

**Python.** 3.12, `mypy --strict`, Ruff with a strict rule set, Google-style
docstrings on public modules, classes and functions. Functions under about 40
lines, modules under about 300, complexity under 10, no magic values. Comments
explain why, not what.

**Layers.** `api` → `services` → `domain`. `domain` performs no I/O and imports
no framework or SDK. Adapters sit behind `typing.Protocol` and are injected in
`app/api/deps.py`.

**Frontend.** Vanilla ES modules, no framework, no build step, no dependencies.
Pure logic lives apart from DOM code so `node --test` can import it. JSDoc
typedefs on API payloads.

**Prompts** live in `app/prompts/*.md` with `PROMPT_VERSION` in
`app/constants.py`. Bump it when wording changes: it is part of the cache key,
so a stale result can never be served under new wording.

**Tests** never touch the network. `LLM_PROVIDER=fake` is the default
everywhere, and the fake provider quotes real clause text so the whole pipeline
is exercised rather than bypassed.

**Commits** follow Conventional Commits. Small and logical.

## Adding things without writing code

Much of the product is data, on purpose.

| To add | Do this |
| --- | --- |
| A letter template | A folder under `app/templates/drafts/` with `template.md.j2` and `fields.json` |
| A help resource | An entry in `app/data/resources.json`, with `source_url` and `verified_on` |
| A glossary term | An entry in `app/data/glossary.json`, with all three languages |
| A checklist | `app/data/checklists/<doc_type>.json`, plus the enum member |
| A law transition | See `docs/DATA.md`. Official source required |
| An interface string | All three of `frontend/i18n/*.json`. A test enforces parity |

## Where to look first

| I want to change | Start at |
| --- | --- |
| How a quote is matched | `app/domain/verification.py` |
| What the model is asked | `app/prompts/*.md` and `builder.py` |
| How a document becomes clauses | `app/domain/segmentation.py` |
| A new endpoint | `app/api/routes/`, then `app/services/` |
| How a result is displayed | `frontend/js/views/` |
| The comparison table | `frontend/js/views/table.js`, one component for all four tables |
| Exported files | `app/rendering/`, all three from one `DocumentModel` |
