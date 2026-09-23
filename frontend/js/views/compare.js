/**
 * Comparing two documents: versions of one, or two competing offers.
 *
 * Both modes render through the shared table in `table.js`, so a comparison
 * looks and behaves the same wherever it appears, and exports match the screen.
 */

import { el } from '../dom.js';
import { statements } from './evidence.js';
import {
  captionFor,
  comparisonTable,
  diffFragment,
  filterRows,
  impactLabel,
  tableControls,
} from './table.js';

const FILTERS = [
  { id: 'all', key: 'compare.filterAll' },
  { id: 'changed', key: 'compare.filterChanged' },
  { id: 'high', key: 'compare.filterHigh' },
];

let activeFilter = 'all';

/**
 * Render the compare tab.
 *
 * @param {object} deps `{ t, state, samples, onCompare, clauseById, onShow }`.
 * @returns {HTMLElement} The tab body.
 */
export function compareView(deps) {
  const { t, state } = deps;
  return el('div', { className: 'stack' }, [
    picker(deps),
    el('p', { className: 'source-note', text: t('compare.neutral') }),
    state.compare ? resultTable(state.compare, deps) : el('p', { className: 'empty-state', text: t('compare.uploadSecond') }),
  ]);
}

/**
 * Render the chooser for the second document.
 *
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The chooser.
 */
function picker({ t, samples, onCompare, state }) {
  const modeSelect = el(
    'select',
    { id: 'compare-mode' },
    [
      el('option', { attrs: { value: 'versions' }, text: t('compare.versions') }),
      el('option', { attrs: { value: 'alternatives' }, text: t('compare.alternatives') }),
    ],
  );

  const others = (samples || []).filter((sample) => sample.title !== state.document?.title);
  const otherSelect = el(
    'select',
    { id: 'compare-other' },
    others.map((sample) => el('option', { attrs: { value: sample.id }, text: sample.title })),
  );

  return el('div', { className: 'card stack-sm' }, [
    el('div', { className: 'field' }, [
      el('label', { attrs: { for: 'compare-mode' }, text: t('compare.heading') }),
      modeSelect,
    ]),
    el('div', { className: 'field' }, [
      el('label', { attrs: { for: 'compare-other' }, text: t('compare.uploadSecond') }),
      otherSelect,
    ]),
    el('button', {
      type: 'button',
      className: 'btn btn--primary',
      text: t('compare.heading'),
      onclick: () => onCompare({ mode: modeSelect.value, otherSampleId: otherSelect.value }),
    }),
  ]);
}

/**
 * Render the comparison as the shared table, with its controls.
 *
 * @param {object} result The `/compare` result.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The table and its controls.
 */
function resultTable(result, deps) {
  const { t } = deps;
  const rows = result.mode === 'versions' ? versionRows(result, deps) : alternativeRows(result, deps);
  const shown = filterRows(rows, activeFilter);
  const holder = el('div', { className: 'stack-sm' });

  holder.append(
    tableControls(
      {
        name: 'compare-filter',
        filters: FILTERS.map((filter) => ({ id: filter.id, label: t(filter.key) })),
        active: activeFilter,
        count: t('document.clauses', { count: shown.length }),
        onFilter: (id) => {
          activeFilter = id;
          holder.replaceWith(resultTable(result, deps));
        },
        onExport: (format) => deps.onExport?.({ format, comparison: result }),
      },
      { t },
    ),
    comparisonTable(
      {
        caption: result.caption || captionFor(rows, t),
        columns:
          result.mode === 'versions'
            ? [t('compare.clause'), t('compare.before'), t('compare.after'), t('compare.whatChanged'), t('compare.impact')]
            : [t('compare.topic'), t('compare.documentA'), t('compare.documentB'), t('compare.difference')],
        rows: shown,
      },
      { t },
    ),
  );
  return holder;
}

/**
 * Build the rows for a version comparison.
 *
 * @param {object} result The comparison.
 * @param {object} deps Render dependencies.
 * @returns {object[]} Table rows.
 */
function versionRows(result, deps) {
  const { t } = deps;
  return (result.pairs || []).map((pair) => ({
    id: pair.label,
    change: pair.change,
    impact: pair.severity,
    header: pair.label || pair.after_clause_id || pair.before_clause_id,
    cells: [
      pair.before_text ? { text: pair.before_text } : { empty: t('compare.notInVersion') },
      pair.after_text ? { text: pair.after_text } : { empty: t('compare.notInVersion') },
      changedCell(pair, deps),
      pair.impact ? { text: pair.impact, badge: impactLabel(pair.severity, t) } : { empty: t('compare.notSpecified') },
    ],
  }));
}

/**
 * Build the "what changed" cell: the word-level diff, then the explanation.
 *
 * @param {object} pair One aligned clause pair.
 * @param {object} deps Render dependencies.
 * @returns {object} The cell.
 */
function changedCell(pair, deps) {
  const { t } = deps;
  if (!pair.diff?.length && !pair.what_changed?.length) {
    return { empty: t('compare.notSpecified') };
  }

  const holder = el('div', { className: 'stack-sm' });
  if (pair.diff?.length) holder.append(el('p', { className: 'flush' }, [diffFragment(pair.diff, t)]));
  if (pair.what_changed?.length) holder.append(statements(pair.what_changed, deps));
  return { node: holder };
}

/**
 * Build the rows for a comparison of two alternatives.
 *
 * @param {object} result The comparison.
 * @param {object} deps Render dependencies.
 * @returns {object[]} Table rows.
 */
function alternativeRows(result, deps) {
  const { t } = deps;
  return (result.rows || []).map((row) => ({
    id: row.topic_id,
    change: row.a_status === row.b_status ? 'unchanged' : 'changed',
    header: row.topic,
    cells: [
      row.a_statements?.length ? { node: statements(row.a_statements, deps) } : { empty: t('compare.notSpecified') },
      row.b_statements?.length ? { node: statements(row.b_statements, deps) } : { empty: t('compare.notSpecified') },
      row.difference ? { text: row.difference } : { empty: t('compare.notSpecified') },
    ],
  }));
}
