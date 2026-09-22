# Security

## Reporting a vulnerability

Open a private security advisory on the repository, or email the maintainers.
Please do not open a public issue for an unpatched vulnerability. We will
acknowledge within a few days.

## Threat model

NyayaLens takes a file from an untrusted person, puts its contents through a
language model, and hands back documents. Each of those three steps is a place
where something can go wrong.

| Asset | Threat | Mitigation | Where |
| --- | --- | --- | --- |
| The reader's trust | The model states something the document does not say | Every quote is matched against the clause it names; unmatched statements are removed and the removal is reported | [`domain/verification.py`](app/domain/verification.py) |
| The reader's trust | The model invents a figure | Every digit in a statement must appear in one of its verified quotes | `_figures_are_supported` in [`verification.py`](app/domain/verification.py) |
| The reader's trust | The model asserts a citation is genuine | `verified`, `score` and spans exist only on domain models and are set only by the verifier; model output is a separate class | [`llm/schemas.py`](app/adapters/llm/schemas.py) vs [`domain/models.py`](app/domain/models.py) |
| The reader's trust | A generated letter carries an invented number | Slot lock rejects model wording containing a figure, date or contact detail outside a slot; the fact audit fails the export if a figure is not a confirmed fact | [`drafting/slots.py`](app/domain/drafting/slots.py), [`fact_audit.py`](app/domain/drafting/fact_audit.py) |
| The reader's trust | A fabricated law mapping | Mappings are packaged data with a source and a review status; unreviewed rows are hidden; the model is never asked what a section maps to | [`docs/DATA.md`](docs/DATA.md) |
| The model's instructions | A document instructs the model | Delimiters neutralised; untrusted-data rule; schema-constrained output; the verifier, which an injected claim cannot satisfy; a warning to the reader | [`prompts/builder.py`](app/prompts/builder.py), [`system.md`](app/prompts/system.md) |
| Personal data | Identifiers reach a third party | Aadhaar (Verhoeff-checked), PAN, Indian mobile numbers and email addresses are masked at ingestion, before any model call | [`domain/redaction.py`](app/domain/redaction.py) |
| Personal data | Document text ends up in logs | Logs carry metadata only: sizes, counts, timings, token usage, a request id | [`logging_config.py`](app/logging_config.py) |
| Personal data | A rejected value is echoed back | Validation errors name fields and messages, never submitted values | [`api/errors.py`](app/api/errors.py) |
| Personal data | Documents accumulate | No persistence. One bounded, expiring in-memory cache; "Clear this document" purges it | [`adapters/cache.py`](app/adapters/cache.py) |
| The server | A malicious upload | Type decided by magic bytes, cross-checked; size enforced while streaming; page limit; DOCX zip-bomb guard; password-protected PDFs refused | [`adapters/documents.py`](app/adapters/documents.py) |
| The server | A zip bomb | An archive expanding past 120× its compressed size, or past 80 MB, is refused before expansion | `_guard_zip_bomb` |
| The server | Server-side request forgery through the PDF renderer | WeasyPrint is given a fetcher that refuses every URL | [`rendering/pdf.py`](app/rendering/pdf.py) |
| The server | Template injection | Sandboxed Jinja with `StrictUndefined`; user input is only ever data passed in, never template source; every interpolated value is Markdown-escaped | [`services/drafting.py`](app/services/drafting.py) |
| The server | Cost exhaustion | Per-IP rate limiting, a stricter budget on exports, a global model-call semaphore, timeouts, output token caps | [`main.py`](app/main.py), [`llm/gemini.py`](app/adapters/llm/gemini.py) |
| The browser | Cross-site scripting through document text | No `innerHTML` anywhere. DOM is built from `createElement` and `textContent`; highlights and diffs from `<mark>`, `<ins>` and `<del>` nodes | [`frontend/js/dom.js`](frontend/js/dom.js) |
| The browser | Script injection through a third party | `script-src 'self'` with no `unsafe-inline`, no `unsafe-eval`, no CDN. The app carries zero inline scripts and zero inline styles | [`api/middleware.py`](app/api/middleware.py) |
| Credentials | A key in the repository | Env vars only; `.env` git-ignored; Secret Manager on Cloud Run; gitleaks in CI; Vertex AI needs no key at all | [`scripts/deploy.sh`](scripts/deploy.sh) |
| Supply chain | A compromised dependency | Fully pinned `requirements.txt` including transitive packages; `pip-audit` and Dependabot; workflow permissions `contents: read`; actions pinned | [`.github/`](.github/) |

## Response headers

Set by middleware on every response, including errors, and asserted by
[`tests/api/test_security.py`](tests/api/test_security.py).

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self';
  img-src 'self' data:; media-src 'self' blob:; font-src 'self'; connect-src 'self';
  object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'
X-Content-Type-Options: nosniff
Referrer-Policy: no-referrer
Permissions-Policy: camera=(), geolocation=(), microphone=(), payment=(), usb=()
Cross-Origin-Opener-Policy: same-origin
Cross-Origin-Resource-Policy: same-origin
Cross-Origin-Embedder-Policy: require-corp
Strict-Transport-Security: max-age=31536000; includeSubDomains
```

There is no CORS header, because the browser application is served from the same
origin as the API.

The policy has no exceptions, and that is load-bearing rather than decorative:
during development the browser blocked the application's own inline `style`
attributes, and they were replaced with classes rather than the policy being
loosened.

## Input limits

Every one is a validated field, not a convention.

| Input | Limit | Enforced by |
| --- | --- | --- |
| Upload size | `MAX_UPLOAD_MB`, default 10 | ASGI middleware, while streaming |
| Page count | `MAX_PAGES`, default 60 | the PDF reader |
| Document text | `MAX_DOCUMENT_CHARS`, default 400,000 | ingestion, which truncates and says so |
| Clauses | `MAX_CLAUSES`, default 1,500 | the request schema |
| Question | 1,000 characters | the request schema |
| Conversation history | 4 turns | the request schema |
| Fact fields | each field's own `max_length` | the template's `fields.json` |
| Quote | 40 words | the verifier, which rejects longer ones |
| Requests | `RATE_LIMIT_PER_MINUTE` per IP | slowapi |
| Exports | `EXPORT_RATE_LIMIT_PER_MINUTE` per IP | slowapi |
| In-flight model calls | `LLM_MAX_CONCURRENCY` | a process-wide semaphore |

## Privacy

- **Masked before anything leaves the process.** Aadhaar numbers (twelve digits
  passing the Verhoeff checksum, so ordinary reference numbers stay readable),
  PAN numbers, Indian mobile numbers and email addresses. The reader is told how
  many were hidden.
- **Nothing is stored.** No database, no object storage, no temporary files. The
  only server-side state is a bounded TTL cache, and "Clear this document"
  empties it for that document.
- **Logs are metadata.** Sizes, counts, timings, token usage, a request id.
  Never document text, questions, answers or facts.
- **Designed with the principles of India's DPDP Act 2023 in mind** —
  minimisation, purpose limitation, no retention. That is a description of the
  design, not a claim of compliance, which only a review can establish.
- **The model provider's terms are the provider's.** Google treats free-tier
  Gemini API data differently from paid tiers and Vertex AI. The README says so,
  and recommends Vertex AI for anything real.

## Running securely

- Use Vertex AI with a least-privilege service account. Then no API key exists.
- If you must use an API key, put it in Secret Manager and inject it at deploy
  time. Never pass it on a command line or commit it.
- The container runs as uid 10001 with no shell, carries no build tools and no
  dev dependencies.
- Run uvicorn with `--proxy-headers` behind Cloud Run, or rate limiting will see
  the load balancer instead of the caller. The Dockerfile does this.
- Keep `LAW_DATA_SHOW_UNREVIEWED=false` in production until the law rows have
  been checked. See [`docs/DATA.md`](docs/DATA.md).
