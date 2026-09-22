# 4. Stateless API; the browser holds the document

Status: accepted · 2026-09-22

## Context

Analysing a document takes several requests: an overview, a review, then
questions. Each needs the clause map. The obvious design stores the document
server-side under a session id.

## Decision

The browser holds the clause map and sends it with every request. The server
stores nothing durable. The only server-side state is a bounded, expiring
in-memory cache keyed by a hash of the content, the operation, the parameters,
the prompt version and the model id.

## Rationale

**"Nothing is stored" becomes true rather than aspirational.** There is no
database to forget to purge, no retention policy to write and then not follow,
no backup quietly holding someone's rental agreement. The claim in the privacy
notice is a statement about the architecture.

**Horizontal scaling comes free.** Any instance can serve any request. A cache
miss costs a model call, not a wrong answer. Cloud Run can scale to zero and
back without losing a session.

**Nothing to leak.** No session identifier to steal, no stored document to
enumerate.

## Consequences

**Good.** Cloud Run needs no session affinity. Closing the tab really does
discard the document.

**The cost.** The clause map travels on every request, tens of kilobytes on a
long document, and it arrives as untrusted input. Both are handled: GZip
compresses the request, and the document is a validated Pydantic model with
caps on clause count and total length. A test asserts a clause map outside the
limits is refused.

**A consequence worth naming.** The browser is the only copy. Refreshing the
page loses the analysis. For a tool used in one sitting that is an acceptable
trade for the privacy property, and the samples make it cheap to start again.
