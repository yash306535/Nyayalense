/**
 * Words in the document, explained.
 *
 * The document's own definition always wins, and is shown with the clause it
 * came from. Where the document defines nothing, a reviewed general meaning is
 * offered and labelled as one, so the two are never confused.
 */

import { el, icon } from '../dom.js';

/**
 * Decide which terms are worth explaining for this document.
 *
 * Pure, so `node --test` covers it.
 *
 * @param {object} doc The ingested document.
 * @param {object[]} entries Every packaged glossary entry.
 * @returns {object[]} Terms to show: `{ term, meaning, clauseId, isOwn }`.
 */
export function termsInDocument(doc, entries) {
  const defined = new Map(
    (doc?.defined_terms || []).map((entry) => [entry.term.toLowerCase(), entry]),
  );
  const text = (doc?.clauses || []).map((clause) => clause.text).join(' ').toLowerCase();

  const own = [...defined.values()].map((entry) => ({
    term: entry.term,
    meaning: entry.definition,
    clauseId: entry.clause_id,
    isOwn: true,
  }));

  const general = (entries || [])
    .filter((entry) => {
      const names = [entry.term, ...(entry.aliases || [])].map((name) => name.toLowerCase());
      return names.some((name) => text.includes(name)) && !defined.has(entry.term.toLowerCase());
    })
    .map((entry) => ({ term: entry.term, entry, isOwn: false }));

  return [...own, ...general].sort((a, b) => a.term.localeCompare(b.term));
}

/**
 * Render the glossary section.
 *
 * A disclosure rather than a hover popover: a definition that only appears on
 * hover is one a keyboard or touch user cannot reach.
 *
 * @param {object[]} terms From `termsInDocument`.
 * @param {object} deps `{ t, language, onShow }`.
 * @returns {HTMLElement|null} The section, or null when there is nothing to explain.
 */
export function glossaryView(terms, { t, language, onShow }) {
  if (!terms.length) return null;

  return el('details', { className: 'panel' }, [
    el('summary', { className: 'panel__header pointer' }, [
      el('strong', { text: t('overview.glossary') }),
    ]),
    el('div', { className: 'panel__body' }, [
      el(
        'dl',
        { className: 'flush' },
        terms.flatMap((item) => [
          el('dt', { className: 'strong', text: item.term }),
          el('dd', { className: 'gap-below' }, [
            el('p', { className: 'flush', text: meaningOf(item, language) }),
            item.isOwn
              ? el('button', {
                  type: 'button',
                  className: 'btn btn--small btn--quiet',
                  onclick: () => onShow(item.clauseId, null),
                }, [icon('seal'), t('overview.definedHere')])
              : el('span', { className: 'chip', text: t('overview.generalMeaning') }),
          ]),
        ]),
      ),
    ]),
  ]);
}

/**
 * Pick the wording to show for one term.
 *
 * @param {object} item A term from `termsInDocument`.
 * @param {string} language The UI language.
 * @returns {string} The document's own definition, or the general meaning.
 */
function meaningOf(item, language) {
  if (item.isOwn) return item.meaning;
  return item.entry.meaning?.[language] || item.entry.meaning?.en || '';
}
