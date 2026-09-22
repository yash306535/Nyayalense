# 2. Send the whole document, not retrieved chunks

Status: accepted · 2026-09-22

## Context

The usual architecture for question answering over documents is retrieval: embed
chunks, search, send the top results. It exists because documents are larger
than context windows.

## Decision

Send the whole document, as numbered clauses, in every call. No vector database,
no embeddings, no retrieval step.

## Rationale

**The documents fit.** A rental agreement, an offer letter, a policy or a notice
is a few thousand tokens. The premise retrieval solves does not hold here.

**A retrieval miss would be indistinguishable from a real absence.** If chunk
selection misses the clause that answers the question, the model reports
`not_found` and the reader is told their document does not say something it
does say. Since the product's central promise is that `not_found` is
trustworthy, a silent recall failure underneath it is the worst possible bug.

**Cross-clause reasoning needs every clause.** Finding that clause 9 says 30 days
while clause 10 says 60 requires both in context. Retrieval on "notice period"
might return either.

**The prefix is cacheable.** System instruction and document block are
byte-identical across every call about one document, so implicit context caching
reuses those tokens. Retrieval would vary the prefix per question and defeat it.

**It removes a whole subsystem.** No embedding model, no vector store, no
chunking strategy, no index to keep in step with the document.

## Consequences

**Good.** No recall failures. Contradiction detection works. The prompt prefix
caches. The architecture is smaller.

**The cost.** Input tokens scale with document size, and a document larger than
the window cannot be analysed in one call. `MAX_DOCUMENT_CHARS` bounds this at
400,000 characters; beyond that the document is truncated and the reader is told.

**If that stops being enough**, the first move is clause-level pre-selection for
the review prompt only, keeping the full document for questions. Retrieval for
Q&A would reintroduce exactly the failure this decision avoids.
