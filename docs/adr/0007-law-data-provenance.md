# 7. Law data is sourced data, and ships unreviewed rather than unsourced

Status: accepted · 2026-09-22

## Context

On 1 July 2024 India replaced the Indian Penal Code, the Code of Criminal
Procedure and the Indian Evidence Act. Notices still cite the old sections, and
people receiving them need to know what those correspond to now.

A language model will answer "what is IPC 420 now?" instantly and confidently.
It will also be wrong often enough to matter, and a wrong section number in a
criminal matter is not a small error.

## Decision

Mapping is data, never inference.

`app/data/laws/mappings/*.json` holds rows read from the correspondence tables
published by the Bureau of Police Research & Development. Every row carries the
document and page it came from, a `review_status`, and a `verified_on` date once
someone has checked it. `scripts/build_law_data.py` extracts rows from the
official PDFs; a person then checks each against its source page.

The model is never asked what a section maps to.

## Two rules that follow

**Unreviewed rows are hidden.** A row stays `extracted` until a person has
checked it, and rows in that state are filtered out of every lookup unless
`LAW_DATA_SHOW_UNREVIEWED` is on. When shown, each carries a visible "Not yet
reviewed" label.

**No statutory text ships unsourced.** `app/data/laws/texts/` is empty, and a
test asserts it. Writing statutory text from memory is the exact failure this
product exists to prevent. The interface says "The full text of this section is
not stored in NyayaLens. Read it on India Code." When texts are added from India
Code, the diff, the punishment extraction and the plain-language description
switch on by themselves — and that description is generated only from the two
stored texts, through the same verifier as everything else.

## What ships today, and why

102 seed rows, **all marked `extracted`**, each naming its source as "Seed row
drafted for NyayaLens. NOT extracted from the official source." They are
therefore hidden by default.

This is deliberate. They give the schema, the parser, the lookup, the interface
and the tests something real to work against, and they give whoever verifies the
data a starting point — without any of them being shown to a reader as checked.
The alternative, shipping nothing, would have left the whole feature untested.

## Traps the tests enforce

Some rows are dangerous to get wrong, so they are asserted rather than trusted:
IPC 124A is never presented as a renumbering; IPC 377 and 497 are
`no_direct_equivalent`; nothing mapping to BNS 302 describes murder; IPC 498A is
a split into BNS 85 and 86.

## Consequences

**Good.** No fabricated section numbers are possible, because no code path asks a
model for one. Every row shows its source and status. An unknown section returns
nothing plus near-miss suggestions.

**The cost.** Coverage is limited to what has been extracted and checked, and a
section outside the data returns nothing. That is the right failure: silence is
recoverable, a wrong section number is not.

**A standing obligation.** These are a police training aid, not a statutory
instrument, and correspondence is not equivalence. The interface says so on
every row, and never says which section applies to anyone's situation.
