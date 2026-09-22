/**
 * The one comparison table.
 *
 * Every comparison in the product uses this component: document versions,
 * competing offers, old law against new, and the references found in a
 * document. One design means one set of semantics to get right, and exports
 * that reproduce the same structure.
 */

import { el, icon, srOnly } from '../dom.js';

/**
 * Build a comparison table.
 *
 * @param {object} spec The table.
 * @param {string} spec.caption A sentence summarising the result.
 * @param {string[]} spec.columns Column headings, the first being the row header.
 * @param {object[]} spec.rows Rows: `{ header, cells, impact, id }`.
 * @param {object} deps `{ t }`.
 * @returns {HTMLElement} A scroll container wrapping the table.
 */
export function comparisonTable({ caption, columns, rows }, { t }) {
  const captionId = `caption-${Math.random().toString(36).slice(2, 9)}`;

  const table = el('table', { className: 'ctable' }, [
    el('caption', { id: captionId, text: caption }),
    el('thead', {}, [
      el(
        'tr',
        {},
        columns.map((column) => el('th', { attrs: { scope: 'col' }, text: column })),
      ),
    ]),
    el(
      'tbody',
      {},
      rows.map((row) => tableRow(row, t)),
    ),
  ]);

  // A scroll container must be reachable by keyboard and named, or a keyboard
  // user cannot scroll it and a screen-reader user does not know what it is.
  return el(
    'div',
    {
      className: 'table-wrap',
      attrs: { role: 'region', tabindex: '0', 'aria-labelledby': captionId },
    },
    [table],
  );
}

/**
 * Build one row.
 *
 * @param {object} row `{ header, cells, impact, id }`.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The row.
 */
function tableRow(row, t) {
  return el(
    'tr',
    { dataset: row.impact ? { impact: row.impact } : {}, attrs: { 'data-row': row.id || '' } },
    [
      el('th', { attrs: { scope: 'row' } }, cellContent(row.header, t)),
      ...row.cells.map((cell) => el('td', { className: cell?.numeric ? 'num' : '' }, cellContent(cell, t))),
    ],
  );
}

/**
 * Render a cell.
 *
 * A blank cell is never left blank: it says what the absence means.
 *
 * @param {object|string|null} cell The cell.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {(Node|string)[]} The cell's children.
 */
function cellContent(cell, t) {
  if (cell === null || cell === undefined || cell === '') {
    return [el('span', { className: 'empty-cell', text: t('compare.notSpecified') })];
  }
  if (typeof cell === 'string') return [cell];
  if (cell.node) return [cell.node];

  const parts = [];
  if (cell.empty) {
    parts.push(el('span', { className: 'empty-cell', text: cell.empty }));
  } else if (cell.diff) {
    parts.push(diffFragment(cell.diff, t));
  } else if (cell.text !== undefined) {
    parts.push(el('span', { text: cell.text }));
  }
  if (cell.badge) parts.push(cell.badge);
  if (cell.seal) parts.push(cell.seal);
  if (cell.note) parts.push(el('p', { className: 'source-note', text: cell.note }));
  return parts;
}

/**
 * Render a word-level diff.
 *
 * Insertions and deletions each carry visually hidden wording, so the change is
 * never conveyed by colour or strike-through alone.
 *
 * @param {{kind: string, text: string}[]} tokens Diff tokens in reading order.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {DocumentFragment} The rendered diff.
 */
export function diffFragment(tokens, t) {
  const fragment = document.createDocumentFragment();
  for (const token of tokens) {
    if (token.kind === 'added') {
      fragment.append(el('ins', {}, [srOnly(t('a11y.added')), token.text]));
    } else if (token.kind === 'removed') {
      fragment.append(el('del', {}, [srOnly(t('a11y.removed')), token.text]));
    } else {
      fragment.append(document.createTextNode(token.text));
    }
    fragment.append(document.createTextNode(' '));
  }
  return fragment;
}

/**
 * Build the controls that sit above a table.
 *
 * @param {object} spec `{ name, filters, active, count, onFilter, onExport }`.
 * @param {object} deps `{ t }`.
 * @returns {HTMLElement} The control bar.
 */
export function tableControls({ name, filters, active, count, onFilter, onExport }, { t }) {
  const group = el('div', { className: 'filter-group', attrs: { role: 'group' } });
  for (const filter of filters) {
    const id = `${name}-${filter.id}`;
    group.append(
      el('input', {
        type: 'radio',
        id,
        attrs: { name, value: filter.id, checked: filter.id === active },
        onchange: () => onFilter(filter.id),
      }),
      el('label', { attrs: { for: id }, text: filter.label }),
    );
  }

  return el('div', { className: 'table-controls' }, [
    group,
    el('div', { className: 'row' }, [
      el('span', { className: 'source-note', text: count }),
      onExport &&
        el('button', { type: 'button', className: 'btn btn--small', onclick: () => onExport('docx') }, [
          t('draft.downloadWord'),
        ]),
      onExport &&
        el('button', { type: 'button', className: 'btn btn--small', onclick: () => onExport('pdf') }, [
          t('draft.downloadPdf'),
        ]),
    ]),
  ]);
}

/**
 * Decide which rows a filter shows.
 *
 * Pure, so `node --test` covers it.
 *
 * @param {object[]} rows All rows.
 * @param {string} filter `all`, `changed` or `high`.
 * @returns {object[]} The rows to show.
 */
export function filterRows(rows, filter) {
  if (filter === 'changed') {
    return rows.filter((row) => row.change && row.change !== 'unchanged');
  }
  if (filter === 'high') return rows.filter((row) => row.impact === 'high');
  return rows;
}

/**
 * Build the caption sentence for a comparison.
 *
 * @param {object[]} rows All rows.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {string} The caption.
 */
export function captionFor(rows, t) {
  const changes = rows.filter((row) => row.change && row.change !== 'unchanged').length;
  if (changes === 0) return t('compare.captionNone');
  const high = rows.filter((row) => row.impact === 'high').length;
  return t('compare.caption', { changes, high });
}

/**
 * Render an impact label: a coloured rule on the row, an icon and a word.
 *
 * @param {string} impact `high`, `medium` or `low`.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The label.
 */
export function impactLabel(impact, t) {
  return el('span', { className: `badge badge--${impact}` }, [
    icon(impact),
    el('span', { text: t(`review.${impact}`) }),
  ]);
}
