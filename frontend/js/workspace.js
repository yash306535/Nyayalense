/**
 * The reading desk: the document on one side, the assistant on the other.
 *
 * Composition only. Every action arrives as a callback, so this module never
 * reaches back into the controller and the two can be read apart.
 */

import { wireTabs } from './a11y.js';
import { buildBrief, isUseful } from './brief.js';
import { el, fill } from './dom.js';
import { findClause } from './state.js';
import { askView } from './views/ask.js';
import { briefView } from './views/brief.js';
import { compareView } from './views/compare.js';
import { documentPane } from './views/document.js';
import { helpStrip } from './views/help.js';
import { overviewView } from './views/overview.js';
import { reviewView } from './views/review.js';
import { rolePicker } from './views/upload.js';

/** The tabs of the assistant panel, in order. */
export const TABS = ['overview', 'review', 'ask', 'compare', 'brief'];

/**
 * Render both panes.
 *
 * @param {object} dom Cached elements.
 * @param {object} state Current application state.
 * @param {object} actions Callbacks the panes invoke.
 */
export function renderWorkspace(dom, state, actions) {
  if (!state.document) return;
  fill(
    dom['document-pane'],
    documentPane({ t: actions.t, document: state.document, onClear: actions.onClear }),
  );
  renderAssistant(dom, state, actions);
}

/**
 * Render the assistant panel for the active tab.
 *
 * @param {object} dom Cached elements.
 * @param {object} state Current application state.
 * @param {object} actions Callbacks the panel invokes.
 */
export function renderAssistant(dom, state, actions) {
  const { t } = actions;
  const deps = {
    t,
    language: state.language,
    clauseById: (id) => findClause(state, id),
    onShow: actions.onShowClause,
    onHelp: actions.onHelp,
  };

  const tablist = buildTablist(state, t);
  wireTabs(tablist, (tab) => {
    actions.onSelectTab(tab);
    // The panel is rebuilt, which destroys the node that had focus. Without
    // this, arrow-keying along the tabs drops the user out of the tab list.
    document.getElementById(`tab-${tab}`)?.focus();
  });

  const panel = el('div', {
    id: 'tabpanel',
    attrs: { role: 'tabpanel', 'aria-labelledby': `tab-${state.tab}`, tabindex: '0' },
  });
  fill(panel, tabContent(state, deps, actions));

  fill(dom['assistant-pane'], [
    rolePicker({
      t,
      roles: state.suggestedRoles.length ? state.suggestedRoles : ['other'],
      active: state.role,
      onChange: actions.onChangeRole,
    }),
    tablist,
    panel,
  ]);
}

/**
 * Build the tab list, with the roving tabindex the ARIA pattern requires.
 *
 * @param {object} state Current application state.
 * @param {(key: string) => string} t Translation function.
 * @returns {HTMLElement} The tab list.
 */
function buildTablist(state, t) {
  const tablist = el('div', {
    className: 'tablist',
    attrs: { role: 'tablist', 'aria-label': t('nav.check') },
  });
  for (const name of TABS) {
    tablist.append(
      el('button', {
        type: 'button',
        className: 'tab',
        dataset: { tab: name },
        attrs: {
          role: 'tab',
          id: `tab-${name}`,
          'aria-selected': String(name === state.tab),
          'aria-controls': 'tabpanel',
          tabindex: name === state.tab ? '0' : '-1',
        },
        text: t(`tabs.${name}`),
      }),
    );
  }
  return tablist;
}

/**
 * Build the body of the active tab.
 *
 * @param {object} state Current application state.
 * @param {object} deps Render dependencies shared by the views.
 * @param {object} actions Callbacks the views invoke.
 * @returns {HTMLElement} The tab body.
 */
function tabContent(state, deps, actions) {
  if (state.tab === 'overview') {
    return state.overview
      ? overviewView(state.overview, { ...deps, onCalendar: actions.onCalendar })
      : loadingPlaceholder(deps.t);
  }
  if (state.tab === 'review') {
    return state.review
      ? el('div', { className: 'stack' }, [
          reviewView(state.review, deps),
          actions.contextualHelp(deps),
        ])
      : loadingPlaceholder(deps.t);
  }
  if (state.tab === 'ask') {
    return askView({
      ...deps,
      answers: state.answers,
      suggested: actions.suggestedQuestions(),
      onAsk: actions.onAsk,
    });
  }
  if (state.tab === 'compare') {
    return compareView({
      ...deps,
      state,
      samples: actions.samples(),
      onCompare: actions.onCompare,
      onExport: actions.onExportComparison,
    });
  }
  return briefPanel(state, deps, actions);
}

/**
 * Build the brief, or a placeholder while there is nothing verified yet.
 *
 * @param {object} state Current application state.
 * @param {object} deps Render dependencies.
 * @param {object} actions Callbacks the brief invokes.
 * @returns {HTMLElement} The brief.
 */
function briefPanel(state, deps, actions) {
  const brief = buildBrief({
    document: state.document,
    overview: state.overview,
    review: state.review,
    answers: state.answers,
    lawReferences: state.lawReferences,
    checklist: actions.checklist(),
    role: state.role,
  });
  if (!isUseful(brief)) return loadingPlaceholder(deps.t);

  return briefView(brief, {
    ...deps,
    onPrint: () => window.print(),
    onExport: (format) => actions.onExportBrief(format, brief),
  });
}

/**
 * Build the contextual "helpful next steps" strip, once it has loaded.
 *
 * @param {Promise<object[]>} pending The resources being fetched.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} A holder that fills itself when the fetch lands.
 */
export function pendingHelpStrip(pending, deps) {
  const holder = el('div');
  pending
    .then((resources) => {
      const strip = helpStrip(resources, deps);
      if (strip) fill(holder, strip);
    })
    .catch(() => {
      // A missing suggestion strip is not worth an error banner.
    });
  return holder;
}

/**
 * Render a loading placeholder that announces itself as busy.
 *
 * @param {(key: string) => string} t Translation function.
 * @returns {HTMLElement} The placeholder.
 */
export function loadingPlaceholder(t) {
  return el('div', { className: 'stack-sm', attrs: { 'aria-busy': 'true' } }, [
    el('p', { className: 'source-note', text: t('app.loading') }),
    el('div', { className: 'skeleton skeleton-line' }),
    el('div', { className: 'skeleton skeleton-line skeleton-line--md' }),
    el('div', { className: 'skeleton skeleton-line skeleton-line--sm' }),
  ]);
}
