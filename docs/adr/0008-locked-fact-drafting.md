# 8. Locked facts: a model may suggest wording, never a fact

Status: accepted · 2026-09-22

## Context

NyayaLens drafts letters people send: a deposit refund request, a resignation, a
complaint. These carry amounts, dates, names and account numbers.

A model is good at the wording of a formal letter, and cannot be trusted with
the numbers in it. A letter to a landlord claiming the wrong deposit amount is
worse than no letter at all, and the reader has no way to spot it — the wrong
figure looks exactly like the right one.

## Decision

Facts and wording are separated and travel different paths.

**Facts** come from a typed sheet the user fills in and confirms. Some are
prefilled from verified results, each showing the clause it came from. Every
value is validated against its declared type. Download stays disabled until the
user ticks "I've checked these facts".

**Wording** may be suggested by a model for one declared free-text field per
template, and it refers to facts only through `[[slot]]` tokens. Code fills
those from the confirmed facts.

## The slot lock

Suggested wording is rejected if it names an unknown slot, drops a required one,
runs past the word limit, or contains **any digit, month name, email address or
phone number outside a slot**. On rejection the template's own wording is used
and the user is told.

The digit rule is deliberately blunt. A false rejection costs the user a
suggestion; a false acceptance puts an invented number in a letter they will
send.

## The fact audit

Before any file is written, every figure in the rendered `DocumentModel` must be
among the confirmed facts or the template's own constants. Otherwise the export
fails with a typed error and no file is produced.

This is a second gate behind the first, and it catches figures however they
arrived — through the slot lock, through a template edit, through a code change
made later by someone who has not read this file.

## Rationale

**The failure is silent.** Everything else in the product shows its evidence. A
letter does not: the recipient reads a number and believes it.

**Defence in depth.** Typed fields, then the slot lock, then the audit. Three
independent gates, because the cost of one failing is a letter someone sends.

**Also protects against the user's own text.** Every interpolated value is
Markdown-escaped, so a fact containing `**` or `#` prints as written rather than
becoming a heading.

## Consequences

**Good.** No fact in an exported letter came from a model. The audit is a pure
function, tested directly. The interface marks which parts of the preview came
from the reader's own confirmed facts.

**The cost.** Wording help is narrower than a model could give, and a suggestion
that mentions a figure in passing is rejected even when correct. Templates must
declare their slots up front. Both are acceptable prices.

**An honest limitation.** This guarantees a letter contains no invented facts. It
does not guarantee the letter is a good idea to send. Hence "Read this through
before you send it", and a suggestion to see a lawyer when the stakes are high.
