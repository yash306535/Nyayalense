/**
 * The review: checklist, risks, missing protections and internal contradictions.
 *
 * The checklist is labelled as review prompts rather than legal rules, and a
 * missing protection is phrased as something to check, never as a verdict.
 */

import { el, icon } from '../dom.js';
import { questionPrompt, severityBadge, statements, statusBadge, trustBlock } from './evidence.js';

/**
 * Render the review.
 *
 * @param {object} review The `/analysis/review` result.
 * @param {object} deps `{ t, clauseById, onShow, onHelp }`.
 * @returns {HTMLElement} The review.
 */
export function reviewView(review, deps) {
  const { t } = deps;
  const hasHighRisk = (review.risks || []).some((risk) => risk.severity === 'high');

  return el('div', { className: 'stack' }, [
    trustBlock(review.verification, t),
    hasHighRisk &&
      el('div', { className: 'notice notice--warning' }, [
        icon('high'),
        el('div', {}, [
          el('strong', { text: t('review.talkToLawyer') }),
          el('p', { style: 'margin:0.25rem 0 0' }, [
            el('button', {
              type: 'button',
              className: 'btn btn--small',
              text: t('brief.whereToGetHelp'),
              onclick: deps.onHelp,
            }),
          ]),
        ]),
      ]),
    riskSection(review.risks, deps),
    missingSection(review.missing, deps),
    inconsistencySection(review.inconsistencies, deps),
    checklistSection(review.checklist, deps),
  ]);
}

/**
 * Render the risks, most serious first.
 *
 * @param {object[]} risks The risks.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The section.
 */
function riskSection(risks, deps) {
  const { t } = deps;
  const body =
    risks && risks.length > 0
      ? el(
          'ul',
          { className: 'stack', style: 'list-style:none;padding:0' },
          risks.map((risk) =>
            el('li', { className: `risk risk--${risk.severity}` }, [
              el('div', { className: 'row-between' }, [
                el('strong', { text: risk.title }),
                severityBadge(risk.severity, t),
              ]),
              el('p', { text: risk.explanation }),
              statements(risk.statements, deps),
              questionPrompt(risk.question_to_ask, t('review.questionToAsk')),
            ]),
          ),
        )
      : el('p', { className: 'empty-state', text: t('review.noRisks') });

  return panel(t('review.risks'), body);
}

/**
 * Render protections that were not found.
 *
 * @param {object[]} missing The missing items.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement|null} The section, or null when nothing is missing.
 */
function missingSection(missing, deps) {
  const { t } = deps;
  if (!missing || missing.length === 0) return null;

  return panel(
    t('review.missing'),
    el('div', { className: 'stack' }, [
      el('p', { className: 'source-note', text: t('review.missingNote') }),
      el(
        'ul',
        { className: 'stack', style: 'list-style:none;padding:0' },
        missing.map((item) =>
          el('li', { className: 'risk risk--medium' }, [
            el('strong', { text: item.title }),
            el('p', { text: item.why_it_matters }),
            item.closest_clause_ids?.length > 0 &&
              el('div', { className: 'row' }, [
                el('span', { className: 'source-note', text: `${t('review.closestClause')}:` }),
                ...item.closest_clause_ids.map((clauseId) =>
                  el('button', {
                    type: 'button',
                    className: 'btn btn--small btn--quiet',
                    text: deps.clauseById(clauseId)?.label || clauseId,
                    onclick: () => deps.onShow(clauseId, null),
                  }),
                ),
              ]),
            questionPrompt(item.question_to_ask, t('review.questionToAsk')),
          ]),
        ),
      ),
    ]),
  );
}

/**
 * Render places the document disagrees with itself.
 *
 * @param {object[]} inconsistencies The inconsistencies.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement|null} The section, or null when there are none.
 */
function inconsistencySection(inconsistencies, deps) {
  const { t } = deps;
  if (!inconsistencies || inconsistencies.length === 0) return null;

  return panel(
    t('review.inconsistencies'),
    el(
      'ul',
      { className: 'stack', style: 'list-style:none;padding:0' },
      inconsistencies.map((entry) =>
        el('li', { className: 'risk risk--high' }, [
          el('div', { className: 'row' }, [icon('high'), el('strong', { text: entry.title })]),
          el('p', { text: entry.explanation }),
          statements(entry.statements, deps),
        ]),
      ),
    ),
  );
}

/**
 * Render the curated checklist.
 *
 * @param {object[]} checklist The checklist outcomes.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The section.
 */
function checklistSection(checklist, deps) {
  const { t } = deps;
  return panel(
    t('review.checklist'),
    el('div', { className: 'stack' }, [
      el('p', { className: 'source-note', text: t('review.checklistNote') }),
      el(
        'ul',
        { className: 'stack', style: 'list-style:none;padding:0' },
        (checklist || []).map((item) =>
          el('li', { className: 'stack-sm' }, [
            el('div', { className: 'row-between' }, [
              el('span', { text: item.title }),
              statusBadge(item.status, t),
            ]),
            statements(item.statements, deps),
            item.status !== 'found' && questionPrompt(item.question_to_ask, t('review.questionToAsk')),
          ]),
        ),
      ),
    ]),
    true,
  );
}

/**
 * Wrap content in a panel, optionally collapsed.
 *
 * @param {string} title The heading.
 * @param {HTMLElement} content The body.
 * @param {boolean} [collapsed] Whether to render it as a disclosure.
 * @returns {HTMLElement} The panel.
 */
function panel(title, content, collapsed = false) {
  if (collapsed) {
    return el('details', { className: 'panel' }, [
      el('summary', { className: 'panel__header', style: 'cursor:pointer' }, [
        el('strong', { text: title }),
      ]),
      el('div', { className: 'panel__body' }, [content]),
    ]);
  }
  return el('section', { className: 'panel' }, [
    el('div', { className: 'panel__header' }, [el('h3', { style: 'margin:0', text: title })]),
    el('div', { className: 'panel__body' }, [content]),
  ]);
}
