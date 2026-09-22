# 5. Every external service behind a Protocol, with a real fake

Status: accepted · 2026-09-22

## Context

The application calls a language model. It may later call OCR, text-to-speech or
a grounding checker. Each needs credentials, costs money, and is slow and
non-deterministic — three properties that make tests either flaky or absent.

## Decision

Every external service sits behind a `typing.Protocol` in `app/adapters/`,
resolved in `app/api/deps.py` and nowhere else. Services depend on the Protocol,
never on an SDK.

For the language model there is a second implementation, `FakeLLMClient`, and it
is document-aware rather than canned: it reads the same clause map a real model
sees, picks clauses by word overlap with the task, and quotes their real text.

## Rationale

**A canned fake would test the wrong thing.** Returning fixed prose would mean
the verifier never runs on anything real, the highlight offsets are never
exercised, and demo mode could show text no clause contains — the exact failure
the product exists to prevent. Because the fake quotes real text, every quote it
returns verifies, and a test asserts that.

**It makes the whole product runnable with no keys.** `make dev-fake` brings up
every feature. The browser tests drive it. A reviewer can clone and run without
an account.

**It keeps the demo honest.** When a question has no overlap with the document,
the fake returns `not_found`, so the most important state in the product is the
one demo mode reaches by itself.

**Optional services can be genuinely optional.** Each flag is off by default with
a working fallback, so nothing depends on a service being enabled.

## Consequences

**Good.** Tests never touch the network and are deterministic. The application
runs offline. The fake is honest enough that a bug in it is a real bug: during
development it embedded clause labels in statement text, the figure check
correctly rejected them, and the fake was fixed rather than the check weakened.

**The cost.** The fake is real code to maintain, and it must stay in step with
the schemas. A module-level check fails at import if a task has no builder.

**A limitation to state plainly.** The fake proves the pipeline works. It says
nothing about how a real model behaves. That is what `evals/` is for, and why
its report is written only from a real run.
