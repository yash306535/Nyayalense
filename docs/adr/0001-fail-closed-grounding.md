# 1. Fail closed: verify every quote in code

Status: accepted · 2026-09-22

## Context

A language model asked to explain a contract will produce fluent text whether or
not the contract says it. The failure is invisible: a reader cannot tell which
sentences came from their document and which came from what such documents
usually contain. For someone deciding whether to sign, that is the whole risk.

Prompting helps and does not solve it. "Only use the document" reduces the rate;
it does not make the rate zero, and it gives the reader no way to check.

## Decision

The model proposes; code disposes.

Every statement must carry at least one citation: a clause id and a quote. Code
then searches for that quote in the clause it names, after normalising both
sides while keeping an offset map. A statement whose quote cannot be found is
removed before the reader sees it, and the removal is counted and reported.

Every number a statement mentions must appear in one of its verified quotes.

If nothing survives, the result is downgraded to `not_found` rather than
returned as a thinner answer.

Model output and verified output are different Pydantic classes. `verified`,
`score` and spans exist only on the second, and only the verifier sets them.

## Consequences

**Good.** The guarantee is testable, and tested: property-based tests assert
that any substring of a clause verifies and that invented text never does. The
reader sees the evidence, not a claim about it. "This document doesn't say"
becomes a real answer instead of a failure.

**The cost.** A correct statement whose quote drifts too far is removed. That is
the trade we want: a missing true statement is recoverable by reading the
clause, an invented one is not. The removal count is shown, so shrinkage is
visible rather than silent.

**What it does not do.** Verification proves a quote is in the document. It does
not prove the statement is a fair reading of it. Hence the interpretation label,
the `needs_professional` flag, and the disclaimer on every view.
