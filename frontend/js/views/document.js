/**
 * The document pane: a calm page with clause labels in the margin.
 *
 * It also carries the outline and find-in-document, because a citation you
 * cannot navigate to is not evidence a person can actually check.
 */

import { clear, el, fill, highlight, icon } from '../dom.js';
import { focusTarget } from '../a11y.js';

/**
 * Render the document pane.
 *
 * @param {object} deps `{ t, document: doc, onClear }`.
 * @returns {HTMLElement} The pane.
 */
export function documentPane({ t, document: doc, onClear }) {
  const results = el('p', { id: 'search-count', className: 'source-note', attrs: { role: 'status' } });
  const clauses = el('div', { className: 'clauses', id: 'clause-list' });

  const search = el('input', {
    type: 'search',
    id: 'doc-search',
    attrs: { 'aria-describedby': 'search-count', placeholder: t('document.search') },
    oninput: (event) => {
      const count = applySearch(clauses, doc, event.target.value);
      results.textContent = event.target.value
        ? count
          ? t('document.searchResults', { count })
          : t('document.noMatches')
        : '';
    },
  });

  renderClauses(clauses, doc.clauses, new Map());

  return el('div', { className: 'stack' }, [
    warnings(doc, t),
    el('div', { className: 'panel' }, [
      el('div', { className: 'panel__header row-between' }, [
        el('div', {}, [
          el('strong', { text: doc.title || t('document.title') }),
          el('p', {
            className: 'source-note',
            style: 'margin:0',
            text: `${t(`docTypes.${doc.doc_type}`)} · ${t('document.clauses', { count: doc.clauses.length })}`,
          }),
        ]),
        el('button', {
          type: 'button',
          className: 'btn btn--small btn--quiet',
          text: t('document.clear'),
          onclick: onClear,
        }),
      ]),
      el('div', { className: 'panel__body stack' }, [
        el('div', { className: 'field' }, [
          el('label', { className: 'sr-only', attrs: { for: 'doc-search' }, text: t('document.search') }),
          search,
          results,
        ]),
        outline(doc, t),
      ]),
    ]),
    el('article', { className: 'document', attrs: { 'aria-label': t('document.title') } }, [clauses]),
  ]);
}

/**
 * Render the clause list, marking any highlighted ranges.
 *
 * @param {HTMLElement} container Where to render.
 * @param {object[]} clauses The clause map.
 * @param {Map<string, {start: number, end: number}[]>} ranges Highlights per clause.
 */
export function renderClauses(container, clauses, ranges) {
  clear(container);
  for (const clause of clauses) {
    const marks = ranges.get(clause.id) || [];
    container.append(
      el('section', { className: 'clause', id: `clause-${clause.id}`, dataset: { clause: clause.id } }, [
        el('div', { className: 'clause__label', text: clause.label || clause.id }),
        el('div', {}, [
          clause.heading && el('strong', { className: 'clause__heading', text: clause.heading }),
          el('p', { className: 'clause__text' }, [
            marks.length ? highlight(clause.text, marks) : clause.text,
          ]),
        ]),
      ]),
    );
  }
}

/**
 * Highlight a citation's quote and move focus to its clause.
 *
 * @param {object} deps `{ container, clauses, clauseId, citation, onBack, t }`.
 */
export function revealClause({ container, clauses, clauseId, citation, onBack, t }) {
  const ranges = new Map();
  if (citation?.verified) {
    ranges.set(clauseId, [{ start: citation.span_start, end: citation.span_end }]);
  }
  renderClauses(container, clauses, ranges);

  for (const node of container.querySelectorAll('.clause--active')) {
    node.classList.remove('clause--active');
  }
  const target = container.querySelector(`#clause-${CSS.escape(clauseId)}`);
  if (!target) return;
  target.classList.add('clause--active');

  if (onBack) {
    target.append(
      el('p', { style: 'grid-column:1/-1;margin:0.5rem 0 0' }, [
        el('button', {
          type: 'button',
          className: 'btn btn--small btn--quiet',
          text: t('document.backToAnswer'),
          onclick: onBack,
        }),
      ]),
    );
  }
  focusTarget(target);
}

/**
 * Render the outline, built from clause headings.
 *
 * @param {object} doc The document.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The outline, collapsed by default.
 */
function outline(doc, t) {
  const headed = doc.clauses.filter((clause) => clause.heading);
  if (headed.length === 0) return el('div', { hidden: true });

  return el('details', { className: 'outline' }, [
    el('summary', { text: t('document.outline') }),
    el('nav', { attrs: { 'aria-label': t('document.outline') } }, [
      el(
        'ol',
        {},
        headed.map((clause) =>
          el('li', {}, [
            el('a', {
              attrs: { href: `#clause-${clause.id}` },
              text: clause.label ? `${clause.label} ${clause.heading}` : clause.heading,
            }),
          ]),
        ),
      ),
    ]),
  ]);
}

/**
 * Show the search term in every clause that contains it.
 *
 * @param {HTMLElement} container The clause list.
 * @param {object} doc The document.
 * @param {string} term What to find.
 * @returns {number} How many clauses matched.
 */
function applySearch(container, doc, term) {
  const needle = String(term || '').trim().toLowerCase();
  const ranges = new Map();
  if (!needle) {
    renderClauses(container, doc.clauses, ranges);
    return 0;
  }
  let matches = 0;
  for (const clause of doc.clauses) {
    const haystack = clause.text.toLowerCase();
    const found = [];
    let at = haystack.indexOf(needle);
    while (at >= 0) {
      found.push({ start: at, end: at + needle.length });
      at = haystack.indexOf(needle, at + needle.length);
    }
    if (found.length > 0) {
      ranges.set(clause.id, found);
      matches += found.length;
    }
  }
  renderClauses(container, doc.clauses, ranges);
  return matches;
}

/**
 * Render the warnings ingestion produced.
 *
 * @param {object} doc The document.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The warnings, or an empty container.
 */
function warnings(doc, t) {
  const container = el('div', { className: 'stack-sm' });
  const notes = [];

  if ((doc.masked || []).length > 0) {
    const total = doc.masked.reduce((sum, entry) => sum + entry.count, 0);
    const kinds = doc.masked.map((entry) => `${entry.count} ${entry.kind}`).join(', ');
    notes.push({ tone: 'seal', text: `${kinds} — ${total} hidden before analysis.` });
  }
  for (const warning of doc.warnings || []) {
    const key = { addresses_ai: 'addressesAi', truncated: 'truncated', little_text: 'littleText' }[warning];
    if (key) notes.push({ tone: 'warning', text: t(`document.${key}`) });
  }

  for (const note of notes) {
    container.append(
      el('div', { className: `notice notice--${note.tone}` }, [
        icon(note.tone === 'warning' ? 'medium' : 'seal'),
        el('span', { text: note.text }),
      ]),
    );
  }
  return container;
}

export { fill };
