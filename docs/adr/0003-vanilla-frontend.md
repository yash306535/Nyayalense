# 3. Vanilla JavaScript, no framework, no build step

Status: accepted · 2026-09-22

## Context

The audience is people in India checking a rental agreement or a job offer,
often on a mid-range Android phone on a slow connection. The interface is a
document reader, a results panel, some tables and a form.

## Decision

Semantic HTML, modern CSS and vanilla ES modules. No framework, no bundler, no
transpiler, no web fonts, no runtime dependencies at all.

## Rationale

**Weight.** A framework plus its runtime is a few hundred kilobytes before any
application code. Here that is the whole payload, and it buys re-rendering
machinery this application does not need: results arrive once and are rendered
once.

**A strict CSP with no exceptions.** `script-src 'self'` with no `unsafe-inline`
and no `unsafe-eval`, no CDN, no hydration. Several frameworks make that awkward
and some make it impossible. The policy caught the application's own inline
`style` attributes during development, and they were replaced rather than the
policy loosened.

**Control over accessibility semantics.** The reading desk, the tab list, the
comparison table and the clause dialog each need exact ARIA behaviour. Owning
the DOM means owning that, rather than working around a component library's
idea of it.

**No build step.** Edit a file, refresh. Nothing to reproduce in CI, nothing to
audit, no lockfile for the browser.

## Consequences

**Good.** Zero dependencies to audit, and zero axe violations across every view
and both themes. `frontend/package.json` declares no dependencies.

**The cost.** State management and rendering are hand-written. The discipline
that keeps that manageable is separating pure logic from DOM code, so the store,
formatting, translation, brief assembly and table filtering are ordinary modules
that `node --test` imports directly. Seventy-six tests run with no browser.

**Where it would stop paying.** If the interface grew genuinely interactive
surfaces, such as a collaborative editor or a live-updating dashboard, the
re-render bookkeeping would start costing more than a framework.
