/**
 * The Get help directory, and the contextual strip shown after an analysis.
 *
 * Styled as an office register: ruled rows and clear hierarchy, not a grid of
 * identical cards. Every entry shows its official source and the date it was
 * checked, and nothing here is ranked or recommended.
 */

import { el, externalLink, icon } from '../dom.js';
import { formatDate } from '../format.js';

const CATEGORY_ICONS = { legal_aid: 'seal', cyber_crime: 'high', consumer: 'question', law_text: 'check' };

/**
 * Render the full directory, grouped by situation.
 *
 * @param {object[]} resources The entries.
 * @param {object} deps `{ t, language }`.
 * @returns {HTMLElement} The directory.
 */
export function helpView(resources, deps) {
  const { t } = deps;
  const groups = new Map();
  for (const resource of resources) {
    if (!groups.has(resource.category)) groups.set(resource.category, []);
    groups.get(resource.category).push(resource);
  }

  return el('div', { className: 'stack' }, [
    el('p', { className: 'prose', text: t('help.intro') }),
    ...[...groups.entries()].map(([category, entries]) =>
      el('section', { className: 'card', attrs: { 'aria-labelledby': `help-${category}` } }, [
        el('h2', { id: `help-${category}`, text: t(`help.categories.${category}`) }),
        el('ul', { className: 'register' }, entries.map((entry) => resourceRow(entry, deps))),
      ]),
    ),
  ]);
}

/**
 * Render the compact "helpful next steps" strip shown after an analysis.
 *
 * @param {object[]} resources Two or three relevant entries.
 * @param {object} deps `{ t, language }`.
 * @returns {HTMLElement|null} The strip, or null when there is nothing to show.
 */
export function helpStrip(resources, deps) {
  const { t } = deps;
  if (!resources || resources.length === 0) return null;

  return el('section', { className: 'panel', attrs: { 'aria-labelledby': 'next-steps' } }, [
    el('div', { className: 'panel__header' }, [
      el('h2', { id: 'next-steps', className: 'flush', text: t('help.nextSteps') }),
    ]),
    el('div', { className: 'panel__body' }, [
      el('ul', { className: 'register' }, resources.map((entry) => resourceRow(entry, deps))),
    ]),
  ]);
}

/**
 * Render one directory entry.
 *
 * @param {object} resource The entry.
 * @param {object} deps `{ t, language }`.
 * @returns {HTMLElement} The row.
 */
function resourceRow(resource, { t, language }) {
  const purpose = resource.purpose?.[language] || resource.purpose?.en || '';

  return el('li', {}, [
    el('span', { className: 'register__icon' }, [icon(CATEGORY_ICONS[resource.category] || 'check')]),
    el('div', {}, [
      el('p', { className: 'register__name', text: resource.name }),
      el('p', { className: 'register__purpose', text: purpose }),
      el('p', { className: 'register__meta' }, [
        resource.cost && el('span', { className: 'chip', text: resource.cost }),
        ' ',
        t('help.checkedOn', { date: formatDate(resource.verified_on, language) }),
      ]),
    ]),
    el('div', { className: 'register__actions' }, [
      resource.contact?.phone &&
        el('a', {
          className: 'btn btn--primary',
          attrs: { href: `tel:${resource.contact.phone.replace(/\s/g, '')}` },
          text: t('help.call', { number: resource.contact.phone }),
        }),
      resource.contact?.url && externalLink(resource.contact.url, t('help.visit'), t('a11y.newTab')),
    ]),
  ]);
}
