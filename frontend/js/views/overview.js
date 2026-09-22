/**
 * The plain-language overview: summary, parties, key terms, obligations, dates.
 *
 * A term the document does not specify is shown as an explicit absence, never
 * omitted quietly and never filled with what such documents usually say.
 */

import { el, icon } from '../dom.js';
import { formatDate } from '../format.js';
import { questionPrompt, statements, trustBlock } from './evidence.js';

/**
 * Render the overview.
 *
 * @param {object} overview The `/analysis/overview` result.
 * @param {object} deps `{ t, language, clauseById, onShow, onCalendar, glossary }`.
 * @returns {HTMLElement} The overview.
 */
export function overviewView(overview, deps) {
  const { t } = deps;
  const dates = (overview.key_dates || []).filter((date) => date.timing_kind === 'absolute' && date.date);

  return el('div', { className: 'stack' }, [
    trustBlock(overview.verification, t),
    section(t('overview.summary'), statements(overview.summary, deps)),
    overview.parties?.length > 0 && section(t('overview.parties'), partyList(overview.parties, t)),
    overview.key_terms?.length > 0 && section(t('overview.keyTerms'), termList(overview.key_terms, deps)),
    overview.obligations?.length > 0 &&
      section(t('overview.obligations'), obligationList(overview.obligations, deps)),
    overview.key_dates?.length > 0 &&
      section(
        t('overview.keyDates'),
        el('div', { className: 'stack-sm' }, [
          dateList(overview.key_dates, deps),
          dates.length > 0 &&
            el('button', {
              type: 'button',
              className: 'btn',
              text: t('overview.addToCalendar'),
              onclick: () => deps.onCalendar(dates),
            }),
        ]),
      ),
  ]);
}

/**
 * Wrap content in a titled section.
 *
 * @param {string} title The heading.
 * @param {HTMLElement} content The body.
 * @returns {HTMLElement} The section.
 */
function section(title, content) {
  return el('section', { className: 'panel' }, [
    el('div', { className: 'panel__header' }, [el('h2', { className: 'flush', text: title })]),
    el('div', { className: 'panel__body' }, [content]),
  ]);
}

/**
 * Render the parties as the document names them.
 *
 * @param {object[]} parties The parties.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The list.
 */
function partyList(parties, t) {
  return el(
    'ul',
    { className: 'stack-sm plain-list' },
    parties.map((party) =>
      el('li', { className: 'row' }, [
        el('strong', { text: party.name }),
        party.described_as && el('span', { className: 'source-note', text: party.described_as }),
        party.is_user && el('span', { className: 'chip', text: t('overview.you') }),
      ]),
    ),
  );
}

/**
 * Render the key terms, including the ones the document does not state.
 *
 * @param {object[]} terms The key terms.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The list.
 */
function termList(terms, deps) {
  const { t } = deps;
  return el(
    'dl',
    { className: 'stack-sm flush' },
    terms.flatMap((term) => [
      el('dt', { className: 'strong' }, [term.label]),
      el('dd', { className: 'gap-below' }, [
        term.value
          ? el('div', { className: 'stack-sm' }, [
              el('p', { className: 'flush', text: term.value }),
              statements(term.statements, deps),
            ])
          : el('p', { className: 'empty-cell flush', text: t('overview.notSpecified') }),
      ]),
    ]),
  );
}

/**
 * Render what each side must do.
 *
 * @param {object[]} obligations The obligations.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The list.
 */
function obligationList(obligations, deps) {
  const { t } = deps;
  const who = { you: t('overview.you'), other_party: t('overview.otherParty'), both: t('overview.both') };

  return el(
    'ul',
    { className: 'stack plain-list' },
    obligations.map((obligation) =>
      el('li', { className: 'risk risk--low' }, [
        el('div', { className: 'row' }, [
          el('span', { className: 'chip', text: who[obligation.who] || obligation.who }),
          el('strong', { text: obligation.what }),
        ]),
        obligation.timing && el('p', { className: 'source-note tight-y', text: obligation.timing }),
        obligation.consequence &&
          el('p', { className: 'tight-y' }, [
            el('em', { text: obligation.consequence }),
          ]),
        statements(obligation.statements, deps),
      ]),
    ),
  );
}

/**
 * Render the key dates. Relative periods are explained in words, not guessed at.
 *
 * @param {object[]} dates The key dates.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The list.
 */
function dateList(dates, deps) {
  const { language } = deps;
  return el(
    'ul',
    { className: 'stack-sm plain-list' },
    dates.map((date) =>
      el('li', { className: 'row top-aligned' }, [
        icon('check'),
        el('div', {}, [
          el('strong', { text: date.title }),
          date.date && el('p', { className: 'flush', text: formatDate(date.date, language) }),
          date.description && el('p', { className: 'source-note flush', text: date.description }),
          statements(date.statements, deps),
        ]),
      ]),
    ),
  );
}

export { questionPrompt };
