# 6. One DocumentModel for the preview, the Word file and the PDF

Status: accepted · 2026-09-22

## Context

NyayaLens produces documents people send: a letter to a landlord, a brief for a
legal-aid clinic, a comparison table. Each needs an on-screen preview, an
editable Word file and a PDF. Three outputs of the same content.

The tempting shape is three renderers, each formatting from the source data.
They then drift, and the reader discovers the difference after they have sent it.

## Decision

Render once into a typed `DocumentModel` — blocks and inline runs — and render
that to HTML, to Word and to PDF. The pipeline is:

```
Jinja template + confirmed facts → Markdown → DocumentModel → { HTML, docx, PDF }
```

The fact audit runs on the `DocumentModel`, so it guards all three at once.

## Rationale

**The preview is the file.** Not a fair approximation of it.

**One audit point.** Every figure in the finished document is checked against the
confirmed facts once, rather than per renderer, with one renderer inevitably
forgotten.

**Deliberately small.** Headings, paragraphs, lists, tables, quotes and rules.
A letter needs no more, and every extra construct is another way for a user's
text to become markup. HTML is disabled in the Markdown parser, so a tag in a
fact is characters.

## Tool choices

**WeasyPrint** for PDF. It shapes text through Pango and HarfBuzz, so Devanagari
renders correctly rather than as boxes, which rules out most of the alternatives
for a product that explains documents in Hindi and Marathi. It is BSD licensed.
It is also a component that will fetch any URL it is given, so it is given a
fetcher that refuses everything.

**python-docx** for Word, because an editable file is what someone actually
sends. MIT licensed.

**PyMuPDF was rejected** despite being excellent: it is AGPL, which is not
compatible with shipping this under MIT.

## Consequences

**Good.** Three formats that cannot disagree. A4, heading styles, repeating
table headers and document metadata are asserted by tests that open the real
files.

**The cost.** Anything the model cannot express cannot be exported: no columns,
no footnotes, no images. For letters and briefs that has not been a constraint.

**A claim not made.** `PDF_VARIANT` requests `pdf/ua-1`, but WeasyPrint's support
for it is experimental and the output has not been validated with veraPDF. No
PDF/UA conformance is claimed anywhere in this repository.
