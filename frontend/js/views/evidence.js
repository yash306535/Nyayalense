/**
 * Rendering verified statements.
 *
 * This is the one component that makes NyayaLens different from a chat box, so
 * it is shared by every result: each statement is followed by the seal of the
 * clause that backs it, and activating a seal takes you to that clause.
 */

import { el, icon, srOnly } from '../dom.js';
import { removalNote, trustLine } from '../format.js';

/**
 * Render the seal shown beside a verified quote.
 *
 * @param {object} citation A verified citation.
 * @param {object} clause The clause it points at.
 * @param {object} deps `{ t, onShow, fresh }`.
 * @returns {HTMLElement} A button that reveals the clause.
 */
export function seal(citation, clause, { t, onShow, fresh = false }) {
  const reference = clause?.label
    ? t('clause.withPage', {
        name: t('clause.numbered', { label: clause.label }),
        page: clause.page,
      })
    : citation.clause_id;

  return el(
    'button',
    {
      type: 'button',
      className: `seal${fresh ? ' seal--new' : ''}`,
      attrs: { 'data-clause': citation.clause_id },
      onclick: () => onShow(citation.clause_id, citation),
    },
    [
      icon('seal'),
      el('span', { text: t('trust.sealLabel') }),
      el('span', { className: 'seal__ref', text: reference }),
      srOnly(t('clause.showInDocument')),
    ],
  );
}

/**
 * Render one statement and its evidence.
 *
 * @param {object} statement A verified statement.
 * @param {object} deps `{ t, clauseById, onShow, fresh }`.
 * @returns {HTMLElement} The statement block.
 */
export function statementBlock(statement, deps) {
  const seals = (statement.citations || [])
    .filter((citation) => citation.verified)
    .map((citation) => seal(citation, deps.clauseById(citation.clause_id), deps));

  return el('div', { className: 'statement' }, [
    el('p', { className: 'statement__text', text: statement.text }),
    statement.kind === 'interpretation' &&
      el('p', { className: 'source-note', text: deps.t('ask.interpretation') }),
    seals.length > 0 && el('div', { className: 'statement__evidence' }, seals),
  ]);
}

/**
 * Render a list of statements.
 *
 * @param {object[]} statements Verified statements.
 * @param {object} deps `{ t, clauseById, onShow, fresh }`.
 * @returns {HTMLElement} A container, empty when there are no statements.
 */
export function statements(statements_, deps) {
  return el(
    'div',
    { className: 'stack-sm' },
    (statements_ || []).map((statement) => statementBlock(statement, deps)),
  );
}

/**
 * Render the trust line, and the disclosure of anything removed.
 *
 * @param {object} report A verification report.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The trust block.
 */
export function trustBlock(report, t) {
  const line = trustLine(report, t);
  const note = removalNote(report, t);
  return el('div', { className: 'stack-sm' }, [
    el('p', { className: `trust trust--${line.tone}` }, [
      icon(line.tone === 'all' ? 'seal' : line.tone === 'partial' ? 'medium' : 'question'),
      el('span', { text: line.text }),
    ]),
    note && el('p', { className: 'removal-note', text: note }),
  ]);
}

/**
 * Render a severity badge, using an icon, a word and a colour together.
 *
 * Severity is never signalled by colour alone.
 *
 * @param {string} severity `high`, `medium` or `low`.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The badge.
 */
export function severityBadge(severity, t) {
  return el('span', { className: `badge badge--${severity}` }, [
    icon(severity),
    el('span', { text: t(`review.${severity}`) }),
  ]);
}

/**
 * Render a checklist status badge.
 *
 * @param {string} status `found`, `not_found` or `unclear`.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The badge.
 */
export function statusBadge(status, t) {
  const icons = { found: 'check', not_found: 'cross', unclear: 'question' };
  return el('span', { className: `badge badge--${status}` }, [
    icon(icons[status] || 'question'),
    el('span', { text: t(`review.${status}`) }),
  ]);
}

/**
 * Render a "question to ask" prompt.
 *
 * Every dead end offers a next step, so a user never leaves with nothing.
 *
 * @param {string} question What to ask.
 * @param {string} label The heading for it.
 * @returns {HTMLElement|null} The prompt, or null when there is no question.
 */
export function questionPrompt(question, label) {
  if (!question) return null;
  return el('div', { className: 'notice' }, [
    icon('question'),
    el('div', {}, [el('strong', { text: `${label}: ` }), el('span', { text: question })]),
  ]);
}
