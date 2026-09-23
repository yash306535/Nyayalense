/**
 * The table of law references found in the open document.
 *
 * Detected at ingestion by an ordinary parser, then looked up in packaged data.
 * A reference the data does not cover shows as not found rather than as a guess.
 */

import { el } from '../dom.js';
import { comparisonTable } from './table.js';

/**
 * Render the table of references detected in the open document.
 *
 * @param {object[]} references The detected references.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The section.
 */
export function foundInDocument(references, deps) {
  const { t } = deps;
  return el('section', { className: 'stack-sm', attrs: { 'aria-labelledby': 'found-heading' } }, [
    el('h2', { id: 'found-heading', text: t('laws.foundInDocument') }),
    comparisonTable(
      {
        caption: t('laws.foundInDocument'),
        columns: [
          t('laws.referenceAsWritten'),
          t('laws.oldLaw'),
          t('laws.newLaw'),
          t('laws.typeOfChange'),
          t('laws.compare'),
        ],
        rows: references.map((reference) => ({
          id: reference.key,
          header: reference.raw || reference.display,
          cells: [
            { text: `${reference.act.toUpperCase()} ${reference.section}` },
            { empty: t('laws.notFound') },
            { empty: '—' },
            {
              node: el('button', {
                type: 'button',
                className: 'btn btn--small',
                text: t('laws.compare'),
                onclick: () => {
                  const search = document.getElementById('law-search');
                  if (search) {
                    search.value = `${reference.act.toUpperCase()} ${reference.section}`;
                    search.form?.requestSubmit();
                  }
                },
              }),
            },
          ],
        })),
      },
      { t },
    ),
  ]);
}
