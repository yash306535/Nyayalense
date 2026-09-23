/**
 * "How it works, and its limits".
 *
 * Every product that gives people information about their rights owes them a
 * plain account of what it does and does not do. This page is that account, and
 * it is reachable from the footer on every view (WCAG 2.2, 3.2.6).
 */

import { el, externalLink } from '../dom.js';

/**
 * Render the page.
 *
 * @param {object} deps `{ t, meta }`.
 * @returns {HTMLElement} The page.
 */
export function aboutView({ t, meta }) {
  return el('div', { className: 'stack' }, [
    section(t('about.pipeline'), [el('p', { className: 'prose', text: t('about.pipelineBody') })]),

    section(t('about.willAndWont'), [
      el('p', { className: 'prose', text: t('about.willDo') }),
      el('p', { className: 'prose', text: t('about.wontDo') }),
    ]),

    section(t('about.whyNotGeneral'), [
      el('ol', { className: 'prose' }, WHY_POINTS.map((key) => el('li', { text: t(`whyNot.${key}`) }))),
    ]),

    section(t('about.dataSources'), [
      el('p', { className: 'prose', text: t('laws.sourceNote') }),
      el('ul', {}, [
        el('li', {}, [externalLink('https://indiacode.gov.in', 'India Code', t('a11y.newTab'))]),
        el('li', {}, [externalLink('https://bprd.nic.in', 'Bureau of Police Research & Development', t('a11y.newTab'))]),
        el('li', {}, [externalLink('https://nalsa.gov.in', 'NALSA', t('a11y.newTab'))]),
      ]),
    ]),

    section(t('about.whenLawyer'), [el('p', { className: 'prose', text: t('about.whenLawyerBody') })]),

    meta &&
      el('p', { className: 'source-note' }, [
        `${meta.name} ${meta.version} · prompt ${meta.prompt_version}`,
        meta.demo_mode ? ` · ${t('app.demoMode')}: ${t('app.demoExplain')}` : '',
      ]),
  ]);
}

/** The eight reasons this is not a general assistant, kept in one place. */
const WHY_POINTS = [
  'citations',
  'failClosed',
  'deterministic',
  'officialData',
  'workflows',
  'lockedFacts',
  'privacy',
  'accessible',
];

/**
 * Render a titled section.
 *
 * @param {string} title The heading.
 * @param {Node[]} children The body.
 * @returns {HTMLElement} The section.
 */
function section(title, children) {
  return el('section', { className: 'card' }, [el('h2', { text: title }), ...children]);
}
