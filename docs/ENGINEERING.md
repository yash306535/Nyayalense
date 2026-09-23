# Engineering practices

What is actually in this repository, with paths. No marketing language, and
nothing here that the code does not do.

## Code quality

| Practice | Where to see it |
| --- | --- |
| Layered, one-way dependencies: `api` → `services` → `domain` | [`app/`](../app/). `domain/` imports no framework and no SDK |
| Adapters behind `typing.Protocol`, injected in one place | [`adapters/llm/base.py`](../app/adapters/llm/base.py), [`api/deps.py`](../app/api/deps.py) |
| `mypy --strict` over `app/` and `scripts/`, with the Pydantic plugin | [`pyproject.toml`](../pyproject.toml). Clean |
| `Any` only at SDK boundaries, wrapped immediately | [`adapters/llm/gemini.py`](../app/adapters/llm/gemini.py) |
| Ruff with E, F, W, I, N, UP, B, SIM, C4, RET, PTH, PL, RUF, S, C90, D, ANN, ARG, TID, ERA, T20 | [`pyproject.toml`](../pyproject.toml). Clean |
| Complexity capped at 10, arguments at 6 | Ruff `C90`, `PLR0913`. Two functions were refactored into rule lists to satisfy it |
| Google-style docstrings on public modules, classes and functions | Ruff `D`, Google convention |
| Comments explain why, not what | e.g. why the figure check treats claims and evidence differently, in [`verification.py`](../app/domain/verification.py) |
| No magic values | Named constants throughout; Ruff `PLR2004` enforces it |
| No `print`, bare `except`, commented-out code, or TODOs | Ruff `T20`, `ERA`, `BLE`. Broad excepts exist only where an SDK raises several unrelated types, each with a comment |
| Exception hierarchy mapped centrally to RFC 9457 | [`errors.py`](../app/errors.py), [`api/errors.py`](../app/api/errors.py) |
| Data-driven content: adding a template, checklist or resource needs no code | [`app/data/`](../app/data/), [`app/templates/drafts/`](../app/templates/drafts/) |
| Prompts in files, versioned, built by pure functions | [`app/prompts/`](../app/prompts/), `PROMPT_VERSION` in [`constants.py`](../app/constants.py) |
| Frontend: small ES modules, pure logic separated from DOM code | [`frontend/js/`](../frontend/js/). 76 tests import the pure modules directly |
| ESLint flat config, no `console.log` | [`eslint.config.mjs`](../eslint.config.mjs). Clean |
| All tool config in `pyproject.toml`, plus `.editorconfig` and pre-commit | [`pyproject.toml`](../pyproject.toml), [`.pre-commit-config.yaml`](../.pre-commit-config.yaml) |

Measured on this checkout: **no module over 300 lines, no function body over 40
lines, no function over complexity 10.** Several modules were split to get
there, and the splits follow the seams rather than the line count: `overview.py`
and `review.py` are two different analyses; `wording.py` is the one place a model
may touch a letter; `mismatches.py` detects a defect while `amounts.py` only
reads numbers; and the browser's `session.js`, `actions.js` and `main.js`
separate state, behaviour and boot.

## Security

See [`SECURITY.md`](../SECURITY.md) for the full threat model. In brief:

- Uploads typed by magic bytes, size enforced while streaming, page limit,
  zip-bomb guard, encrypted PDFs refused.
- Every field capped by a Pydantic constraint, not a convention.
- Sandboxed Jinja with `StrictUndefined`; user input is only ever data.
- WeasyPrint given a fetcher that refuses every URL.
- Nine security headers on every response, asserted by test. CSP has no
  exceptions: the app ships zero inline scripts and zero inline styles.
- Per-IP rate limiting, a stricter export budget, a global model-call semaphore.
- Identifiers masked before any model call; logs carry metadata only.
- Fully pinned dependencies, `pip-audit`, `bandit`, gitleaks, Dependabot.
- Container: multi-stage, pinned base, non-root uid 10001, no build tools.

## Efficiency

| Practice | Where |
| --- | --- |
| Async endpoints; CPU-bound work off the event loop | `anyio.to_thread` in [`services/exports.py`](../app/services/exports.py) |
| One cacheable prompt prefix per document | [`prompts/builder.py`](../app/prompts/builder.py); asserted by test |
| Overview and review in parallel, each rendered as it lands | [`frontend/js/main.js`](../frontend/js/main.js) |
| Result cache keyed by content, operation, params, prompt version and model | [`adapters/cache.py`](../app/adapters/cache.py) |
| Compare sends only changed pairs | [`services/compare.py`](../app/services/compare.py) |
| No model call for the brief, calendar, defined terms, amounts, doc typing, law lookup or prefill | [`frontend/js/brief.js`](../frontend/js/brief.js), [`domain/`](../app/domain/) |
| Law index built once at startup, keyed both ways; regexes compiled at import | [`domain/laws/lookup.py`](../app/domain/laws/lookup.py) |
| Normalised clause text computed once per request; the verifier searches only the cited clause | `ClauseIndex` in [`verification.py`](../app/domain/verification.py) |
| Preview returns a model; files render only on download, off the event loop | [`api/routes/drafts.py`](../app/api/routes/drafts.py) |
| Optional PDF warm-up at startup | `EXPORT_WARMUP` |
| Frontend: no framework, no bundler, no web fonts; `content-visibility` on long documents | [`frontend/`](../frontend/) |
| GZip, plus `Cache-Control` and ETags on static assets | [`api/middleware.py`](../app/api/middleware.py), Starlette `StaticFiles` |
| Token usage and latency logged per model call | [`adapters/llm/gemini.py`](../app/adapters/llm/gemini.py) |

No latency or token figures are published anywhere in this repository, because
none have been measured against a live model on this checkout. `make eval`
measures them and writes them to `evals/REPORT.md`.

## Testing

| Layer | Count | What it covers |
| --- | --- | --- |
| Unit | most of 570 | Normalisation offset maps, the verifier, amounts, redaction, segmentation, definitions, diff, ICS, document typing, law references, the data files, the renderers, drafting rules, the build script |
| Property-based | within those | Any substring of a clause verifies to the right span; text not in the clause never does; every normalised character maps inside its source |
| API | within those | Every route: success, 400, 404, 413, 415, 422, 429, the problem+json shape, and the security headers |
| Frontend | 76 | The pure modules, and bundle parity across all three languages |
| Browser | 51 | The main flow, a keyboard-only run of it, and axe on every view and state |

- **Coverage: 93%** on `app/`, with the gate at 90.
- **Tests never touch the network.** `LLM_PROVIDER=fake` everywhere.
- **The fake is document-aware**, so the verifier, highlighting and exports are
  exercised for real rather than bypassed.
- **Trap tests** on the law data: BNS 302 is not murder; IPC 124A is never a
  renumbering.
- **Injection tests**: the offer-letter sample instructs AI systems to call it
  fair, and a test asserts the review still reports the risks.
- **Live evaluation** in [`evals/`](../evals/), deliberately outside CI because
  it needs a real key and costs money. Its report is written only from a real run.

CI ([`.github/workflows/ci.yml`](../.github/workflows/ci.yml)) runs the same
commands as `make check`, in five jobs: quality, frontend, backend, browser and
container build.

## Accessibility

See [`ACCESSIBILITY.md`](../ACCESSIBILITY.md). Zero axe violations across every
view, both themes, at 320px and at 200% text, under six rulesets including
`best-practice`. The manual screen-reader checklist is listed as pending, and
nothing claims otherwise.

## Honesty

The practice that governs the rest: **nothing is claimed that the code does not
do.**

- Features designed but not built are listed as "Not built" in the README
  feature table, and their configuration flags are marked "reserved, not
  implemented".
- `evals/REPORT.md` is absent because the suite has not been run on this
  checkout. No latency or accuracy number appears anywhere as a result.
- PDF/UA conformance is not claimed, because the output has not been validated.
- The Hindi and Marathi strings are marked as needing a fluent speaker's review.
- The shipped law rows say plainly, in their own `source` field, that they were
  not extracted from the official PDF — and they are hidden from readers because
  of it.
