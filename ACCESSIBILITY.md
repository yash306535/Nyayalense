# Accessibility

## Conformance target

**WCAG 2.2 Level AA.**

This page reports what has been tested and what has not. An accessibility
statement that only lists the good news is not much use to the person who needs
it.

## What has been tested, and how

### Automated

[`tests/e2e/test_accessibility.py`](tests/e2e/test_accessibility.py) runs
axe-core over every view and state, in both colour schemes, at zero tolerance,
with the `wcag2a`, `wcag2aa`, `wcag21a`, `wcag21aa`, `wcag22aa` and
`best-practice` rulesets. A single violation fails the build.

| Covered | Light | Dark |
| --- | --- | --- |
| Upload, and the loading state | yes | yes |
| Overview, review, answers | yes | yes |
| Comparison table | yes | yes |
| Lawyer brief | yes | yes |
| Law lookup, and the comparison table | yes | yes |
| Get help directory | yes | yes |
| Drafting form and preview | yes | yes |
| How it works | yes | yes |
| Clause dialog, at phone width | yes | — |
| Error state | yes | — |

Also asserted: no horizontal scrolling at 320, 360 or 768 CSS pixels, and none
with text enlarged to 200%.

**Result on this checkout: zero violations.**

### Keyboard

[`tests/e2e/test_keyboard.py`](tests/e2e/test_keyboard.py) walks the main flow
without a pointer: skip link, loading a sample, the tab list, activating a
citation, and asking a question. It also asserts that no interactive element is
removed from the tab order without reason, that focus is visibly ringed, and
that no target is smaller than 24 by 24 CSS pixels.

### Not tested automatically

Everything a machine cannot judge. These are listed as **pending**, and nothing
in this repository claims otherwise.

## Manual screen-reader checklist — pending

Not yet completed. Each line is a thing a tool cannot check for you.

### NVDA with Firefox (Windows)
- [ ] The page announces its title and the demo-mode badge on load.
- [ ] Landmark navigation reaches the header, main and footer.
- [ ] Heading navigation gives a sensible outline on every view.
- [ ] "Reading your document…" is announced when an analysis starts.
- [ ] The trust line is announced when results arrive.
- [ ] A verification seal announces "Verified, Clause 7.2, page 3, show in document".
- [ ] Activating a seal lands on the clause and reads it from the highlight.
- [ ] "Back to the answer" returns focus somewhere useful.
- [ ] In the comparison table, table navigation reads row and column headers.
- [ ] Insertions and deletions are announced as "added" and "removed", not by style.
- [ ] A form error moves focus to the summary and each entry reaches its field.
- [ ] "Word file ready" is announced when a download completes.

### VoiceOver with Safari (macOS and iOS)
- [ ] The rotor lists headings, landmarks and form controls sensibly.
- [ ] On iOS, the clause dialog traps focus and returns it on close.
- [ ] The comparison table is navigable in table mode.
- [ ] Hindi and Marathi text is read in the right voice, not spelled out.

### TalkBack with Chrome (Android)
- [ ] Every control is reachable by swipe, in a sensible order.
- [ ] Targets are large enough to hit reliably.
- [ ] The clause dialog behaves as a dialog.
- [ ] Reading the document pane is not interrupted by the assistant panel.

### Speech input (Voice Control, Voice Access)
- [ ] Every control has a visible label matching its accessible name, so it can
      be spoken. (WCAG 2.5.3 label in name.)

## How the interface is built

- **Landmarks and headings.** One `h1` per view, which stays in the DOM as the
  view changes state. Heading levels never skip.
- **Native elements first.** `button`, `a`, `select`, `dialog`, `details`,
  `table`, `fieldset`. ARIA appears where there is no native equivalent: the tab
  list implements the WAI-ARIA pattern in full, with roving tabindex, arrow
  keys, Home and End.
- **Focus.** One `:focus-visible` ring everywhere, above 3:1 contrast. Activating
  a citation moves focus to the clause and offers a way back. Dialogs trap focus
  and return it. `scroll-padding-top` keeps a focused element clear of the
  sticky header (2.4.11).
- **Announcements.** One polite live region for progress, results and downloads;
  one assertive region for errors. Loading regions carry `aria-busy`.
- **Never colour alone.** Severity is an icon, a word and a colour. Checklist
  status is an icon and a word. Diff insertions and deletions carry visually
  hidden "added:" and "removed:" text.
- **Contrast.** Every token clears 4.5:1 for text against every surface it is
  used on, and 3:1 for interface components, in both themes. The ratios were
  computed rather than eyeballed, and one token was darkened when axe caught it
  at 4.43:1.
- **Reflow.** Usable at 320px. The reading desk collapses when its panes no
  longer fit, rather than at a breakpoint measured in unscaled rem, which is why
  it survives 200% text.
- **Targets.** 24×24 minimum everywhere; 44×44 for the call and visit buttons in
  the help directory.
- **Drag is never the only way.** The drop zone is also a real button (2.5.7).
- **Help stays put.** The footer carries the same links on every view (3.2.6).
- **Asked once.** Role and language are asked once per document (3.3.7).
- **Respects the system.** `prefers-reduced-motion`, `prefers-color-scheme` and
  `forced-colors`. There is exactly one animation, the seal stamping in when
  verification completes, and reduced motion removes it.
- **Forms.** Visible labels, hints tied with `aria-describedby`, `aria-invalid`
  on failures, and an error summary linking to each invalid field. Messages say
  how to fix the problem.

## Language

The interface, explanations and the help directory are available in English,
Hindi and Marathi. `<html lang>` follows the choice, and a block in another
language carries its own `lang`. Quotes always stay in the document's own
language, whatever the interface is set to.

Numbers, money and dates are formatted with `Intl` in `en-IN`, `hi-IN` and
`mr-IN`.

**The Hindi and Marathi strings have not been reviewed by a fluent speaker.**
They are usable and complete, and a test asserts all three bundles carry
identical keys and placeholders, but they need a human read before release.

## Generated files

- **Word** uses built-in heading styles, sets a document title and a language,
  and marks table header rows to repeat across pages. Asserted in
  [`tests/api/test_drafting.py`](tests/api/test_drafting.py).
- **PDF** is A4 with title and language metadata. `PDF_VARIANT` defaults to
  `pdf/ua-1`, but **WeasyPrint's PDF/UA support is experimental and the output
  has not been validated with veraPDF. No PDF/UA conformance is claimed.**

## Known limitations

1. The manual screen-reader checklist above is not complete.
2. Hindi and Marathi strings are unreviewed.
3. Tagged-PDF output is unvalidated.
4. Scanned documents are not supported at all, which is itself a barrier for
   anyone whose only copy is a photograph.
5. There is no read-aloud. A reader who wants the explanation spoken must use
   their own screen reader or their browser's reading mode.

## Feedback

If something here does not work for you, please open an issue. Tell us the page,
what you were using, and what happened. A report about a real barrier is worth
more than any automated check.
