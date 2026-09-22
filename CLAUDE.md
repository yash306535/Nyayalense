# NyayaLens

Grounded explanations of Indian legal documents. Every statement shown to a user
carries a quote that code has matched against the document.

## Commands
- `make dev-fake` — run offline with the deterministic fake provider, no keys
- `make check` — lint, types, security scans and tests (what CI runs)
- `make test` — backend tests with coverage, plus frontend unit tests
- `make e2e` — Playwright and axe tests against the app in fake mode
- `make laws-data` — rebuild law data from the official PDFs in `data_sources/`

## Architecture rules
- Layers are `api` → `services` → `domain`. `domain` has no I/O and no framework
  or SDK imports. Adapters sit behind `typing.Protocol` and are injected in
  `app/api/deps.py`.
- **Nothing reaches the UI unverified.** Model output is a DTO in
  `app/adapters/llm/schemas.py`; only `app/domain/verification.py` may set
  `Citation.verified`, a score or a span. The one crossing point is
  `app/services/grounding.py`.
- "This document doesn't say" is a first-class result. Never fill a gap.
- Law mappings, provision texts, glossary entries and help contacts come from
  packaged data files that record their own source and review date. Never write
  one from memory. See `docs/DATA.md`.
- Drafts contain only facts the user confirmed. A model may suggest wording, and
  refers to facts only through `[[slot]]` tokens that code fills in.
- The API is stateless. The browser holds the clause map and sends it back.
  Nothing is stored; the result cache is in-memory, bounded and expiring.
- Never `innerHTML` with dynamic data. Build DOM with the helpers in
  `frontend/js/dom.js`.

## Conventions
- Python 3.12, `mypy --strict`, Ruff with a strict rule set, Google docstrings.
- Functions ≤ ~40 lines, modules ≤ ~300, complexity ≤ 10, no magic values.
- Comments explain why, not what.
- Frontend is vanilla ES modules with no build step. Pure logic lives apart from
  DOM code so `node --test` can import it.
- Prompts live in `app/prompts/*.md` with `PROMPT_VERSION` in `app/constants.py`.
  Bump it when wording changes; it is part of the cache key.
- Tests never touch the network. `LLM_PROVIDER=fake` is the default.

## Never
- Say whether to sign, predict an outcome, or state what the law requires.
- Commit a secret, or add a dependency that is not permissively licensed.
- Claim in docs anything the code does not do.
