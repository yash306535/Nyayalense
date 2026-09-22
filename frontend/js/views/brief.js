/**
 * Rendering the brief for a lawyer or legal-aid clinic.
 *
 * Built by {@link module:brief} from results that already passed verification,
 * then rendered here for the screen, for print, and for Word and PDF export.
 */

import { el, icon } from '../dom.js';
import { formatDate } from '../format.js';
import { severityBadge } from './evidence.js';

/**
 * Render the brief.
 *
 * @param {object} brief A brief from `buildBrief`.
 * @param {object} deps `{ t, language, onPrint, onExport, onHelp }`.
 * @returns {HTMLElement} The brief.
 */
export function briefView(brief, deps) {
  const { t, language } = deps;

  return el('div', { className: 'stack', id: 'brief' }, [
    el('div', { className: 'row no-print' }, [
      el('button', { type: 'button', className: 'btn', text: t('brief.print'), onclick: deps.onPrint }),
      el('button', {
        type: 'button',
        className: 'btn',
        text: t('draft.downloadWord'),
        onclick: () => deps.onExport('docx'),
      }),
      el('button', {
        type: 'button',
        className: 'btn',
        text: t('draft.downloadPdf'),
        onclick: () => deps.onExport('pdf'),
      }),
    ]),
    el('p', { className: 'prose', text: t('brief.intro') }),

    block(t('brief.summary'), [
      el('p', { text: `${t(`docTypes.${brief.docType}`)} — ${t(`roles.${brief.role}`)}` }),
      ...brief.summary.map((statement) => el('p', { text: statement.text })),
      brief.parties.length > 0 &&
        el(
          'ul',
          {},
          brief.parties.map((party) =>
            el('li', { text: `${party.name}${party.describedAs ? ` — ${party.describedAs}` : ''}` }),
          ),
        ),
      brief.keyTerms.length > 0 &&
        el(
          'dl',
          {},
          brief.keyTerms.flatMap((term) => [
            el('dt', { className: 'strong', text: term.label }),
            el('dd', {
              className: 'gap-below-sm',
              text: term.specified ? term.value : t('overview.notSpecified'),
            }),
          ]),
        ),
    ]),

    brief.risks.length > 0 &&
      block(
        t('brief.topRisks'),
        brief.risks.map((risk) =>
          el('div', { className: `risk risk--${risk.severity} spaced` }, [
            el('div', { className: 'row-between' }, [
              el('strong', { text: risk.title }),
              severityBadge(risk.severity, t),
            ]),
            el('p', { text: risk.explanation }),
            ...risk.statements.map((statement) => quote(statement)),
            risk.questionToAsk && el('p', {}, [el('em', { text: risk.questionToAsk })]),
          ]),
        ),
      ),

    brief.missing.length > 0 &&
      block(
        t('review.missing'),
        el(
          'ul',
          {},
          brief.missing.map((item) =>
            el('li', {}, [el('strong', { text: item.title }), ' — ', item.whyItMatters]),
          ),
        ),
      ),

    brief.inconsistencies.length > 0 &&
      block(
        t('review.inconsistencies'),
        el(
          'ul',
          {},
          brief.inconsistencies.map((entry) =>
            el('li', {}, [el('strong', { text: entry.title }), ' — ', entry.explanation]),
          ),
        ),
      ),

    brief.dates.length > 0 &&
      block(
        t('overview.keyDates'),
        el(
          'ul',
          {},
          brief.dates.map((date) =>
            el('li', {
              text: date.date
                ? `${date.title}: ${formatDate(date.date, language)}`
                : `${date.title}: ${date.description}`,
            }),
          ),
        ),
      ),

    brief.lawReferences.length > 0 &&
      block(
        t('brief.lawReferences'),
        el(
          'ul',
          {},
          brief.lawReferences.map((reference) =>
            el('li', { text: `${reference.act.toUpperCase()} ${reference.section} — "${reference.raw}"` }),
          ),
        ),
      ),

    brief.questions.length > 0 &&
      block(
        t('brief.questions'),
        brief.questions.map((entry) =>
          el('div', { className: 'spaced' }, [
            el('p', {}, [el('strong', { text: entry.question })]),
            entry.answered
              ? el('div', {}, entry.statements.map((statement) => quote(statement)))
              : el('p', { className: 'empty-cell', text: t('ask.notFound') }),
          ]),
        ),
      ),

    brief.factsToHaveReady.length > 0 &&
      block(
        t('brief.factsToHaveReady'),
        el('ul', {}, brief.factsToHaveReady.map((fact) => el('li', { text: fact }))),
      ),

    brief.documentsToBring.length > 0 &&
      block(
        t('brief.documentsToBring'),
        el('ul', {}, brief.documentsToBring.map((item) => el('li', { text: item }))),
      ),

    el('div', { className: 'notice no-print' }, [
      icon('seal'),
      el('div', {}, [
        el('strong', { text: t('brief.whereToGetHelp') }),
        el('p', { className: 'tight' }, [
          el('button', {
            type: 'button',
            className: 'btn btn--small',
            text: t('nav.help'),
            onclick: deps.onHelp,
          }),
        ]),
      ]),
    ]),

    el('p', {
      className: 'source-note',
      text: t('brief.footer', { date: formatDate(new Date().toISOString().slice(0, 10), language) }),
    }),
  ]);
}

/**
 * Render a titled block.
 *
 * @param {string} title The heading.
 * @param {(Node|false)[]|Node} content The body.
 * @returns {HTMLElement} The block.
 */
function block(title, content) {
  return el('section', { className: 'card' }, [
    el('h2', { text: title }),
    ...(Array.isArray(content) ? content : [content]),
  ]);
}

/**
 * Render a verified quote as evidence in the brief.
 *
 * @param {object} statement A statement with verified citations.
 * @returns {HTMLElement} The quote block.
 */
function quote(statement) {
  return el('div', {}, [
    el('p', { className: 'gap-below-xs', text: statement.text }),
    ...statement.citations.map((citation) =>
      el('blockquote', { className: 'quote-evidence' }, [
        el('p', { className: 'flush', text: `"${citation.quote}"` }),
        el('cite', { className: 'source-note', text: citation.clauseId }),
      ]),
    ),
  ]);
}
