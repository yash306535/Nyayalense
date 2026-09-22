/**
 * Application entry point.
 *
 * Wires the store, the router and the views. Everything that touches the DOM
 * lives here or in `views/`; the logic those views depend on lives in modules
 * that `node --test` can import.
 */

import { announce, openDialog, prefersReducedMotion, setBusy, wireTabs } from './a11y.js';
import { ApiError, api } from './api.js';
import { el, fill } from './dom.js';
import { downloadName, trustLine } from './format.js';
import { initialLanguage, translator } from './i18n.js';
import {
  analysisBody,
  answerReceived,
  createStore,
  documentLoaded,
  findClause,
  recentTurns,
  situations,
} from './state.js';
import { buildBrief, isUseful } from './brief.js';
import { aboutView } from './views/about.js';
import { askView } from './views/ask.js';
import { briefView } from './views/brief.js';
import { compareView } from './views/compare.js';
import { documentPane, revealClause } from './views/document.js';
import { draftView } from './views/draft.js';
import { helpStrip, helpView } from './views/help.js';
import { lawsView } from './views/laws.js';
import { overviewView } from './views/overview.js';
import { reviewView } from './views/review.js';
import { rolePicker, uploadPanel } from './views/upload.js';

const SUPPORTED = ['en', 'hi', 'mr'];
const STORAGE_LANGUAGE = 'nyayalens.language';
const STORAGE_THEME = 'nyayalens.theme';
const TABS = ['overview', 'review', 'ask', 'compare', 'brief'];
const ROUTES = ['check', 'laws', 'draft', 'help', 'about'];

const store = createStore();
const bundles = {};
let t = (key) => key;
let samples = [];
let checklist = null;

const dom = {};

/** Cache the elements the controller touches. */
function cacheDom() {
  const ids = [
    'live-polite', 'live-alert', 'demo-badge', 'language-select', 'theme-toggle',
    'upload-panel', 'upload-controls', 'workspace', 'document-pane', 'assistant-pane',
    'laws-pane', 'draft-pane', 'help-pane', 'about-pane', 'clause-dialog',
    'clause-dialog-title', 'clause-dialog-body', 'main',
  ];
  for (const id of ids) dom[id] = document.getElementById(id);
}

/* ------------------------------------------------------------------ boot */

/** Start the application. */
async function start() {
  cacheDom();
  await loadLanguage(
    initialLanguage(SUPPORTED, safeRead(STORAGE_LANGUAGE), navigator.languages || [navigator.language]),
  );
  applyTheme(safeRead(STORAGE_THEME));
  wireChrome();
  window.addEventListener('hashchange', route);

  try {
    const [meta, sampleList] = await Promise.all([api.meta(), api.samples()]);
    samples = sampleList;
    store.set({ meta });
    dom['demo-badge'].hidden = !meta.demo_mode;
  } catch (error) {
    showError(error);
  }

  renderUpload();
  route();
}

/**
 * Load a language bundle and switch to it.
 *
 * @param {string} language One of the supported languages.
 */
async function loadLanguage(language) {
  if (!bundles[language]) {
    const response = await fetch(`/i18n/${language}.json`);
    bundles[language] = await response.json();
  }
  if (language !== 'en' && !bundles.en) {
    bundles.en = await (await fetch('/i18n/en.json')).json();
  }
  t = translator(bundles, language);
  store.set({ language });
  document.documentElement.lang = language;
  safeWrite(STORAGE_LANGUAGE, language);
  applyStaticStrings();
}

/** Fill every element carrying a `data-i18n` key. */
function applyStaticStrings() {
  for (const node of document.querySelectorAll('[data-i18n]')) {
    node.textContent = t(node.dataset.i18n);
  }
  document.title = `${t('app.name')} — ${t('app.tagline')}`;
}

/** Wire the header controls and the dialog. */
function wireChrome() {
  dom['language-select'].value = store.get().language;
  dom['language-select'].addEventListener('change', async (event) => {
    await loadLanguage(event.target.value);
    renderUpload();
    renderWorkspace();
    route();
  });

  dom['theme-toggle'].addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    applyTheme(next);
    safeWrite(STORAGE_THEME, next);
  });

  for (const button of document.querySelectorAll('[data-close-dialog]')) {
    button.addEventListener('click', () => dom['clause-dialog'].close());
  }
}

/**
 * Apply a theme, or follow the system when none is stored.
 *
 * @param {string|null} theme `dark`, `light` or null.
 */
function applyTheme(theme) {
  if (theme === 'dark' || theme === 'light') {
    document.documentElement.dataset.theme = theme;
  } else {
    delete document.documentElement.dataset.theme;
  }
  const dark = document.documentElement.dataset.theme === 'dark';
  dom['theme-toggle'].setAttribute('aria-pressed', String(dark));
  dom['theme-toggle'].textContent = dark ? t('app.lightMode') : t('app.darkMode');
}

/* ----------------------------------------------------------------- router */

/** Show the view named by the URL fragment. */
function route() {
  const name = (location.hash.replace('#/', '') || 'check').split('?')[0];
  const view = ROUTES.includes(name) ? name : 'check';

  for (const candidate of ROUTES) {
    const node = document.getElementById(`view-${candidate}`);
    if (node) node.hidden = candidate !== view;
  }
  for (const link of document.querySelectorAll('.app-nav a')) {
    const current = link.dataset.route === view;
    if (current) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }

  if (view === 'laws') renderLaws();
  if (view === 'draft') renderDraft();
  if (view === 'help') renderHelp();
  if (view === 'about') fill(dom['about-pane'], aboutView({ t, meta: store.get().meta }));
}

/* ------------------------------------------------------------------ views */

/** Render the upload panel. */
function renderUpload() {
  fill(
    dom['upload-controls'],
    uploadPanel({
      t,
      samples,
      demoMode: Boolean(store.get().meta?.demo_mode),
      onFile: (file) => ingest(() => api.upload(file)),
      onPaste: (text) =>
        text.trim() ? ingest(() => api.paste(text, t('document.title'))) : showMessage(t('errors.emptyText')),
      onSample: (id) => ingest(() => api.sample(id)),
    }),
  );
}

/**
 * Ingest a document, then load its analyses.
 *
 * @param {() => Promise<object>} call The API call to make.
 */
async function ingest(call) {
  await withBusy(t('a11y.reading'), async () => {
    const result = await call();
    store.update((state) => documentLoaded(state, result));
    checklist = await api.checklist(result.document.doc_type).catch(() => null);
    dom['upload-panel'].hidden = true;
    dom.workspace.hidden = false;
    renderWorkspace();
    await loadAnalyses();
  });
}

/** Load the overview and the review in parallel, rendering each as it lands. */
async function loadAnalyses() {
  const body = analysisBody(store.get());
  const pane = dom['assistant-pane'];
  setBusy(pane, true);

  const [overview, review] = await Promise.allSettled([api.overview(body), api.review(body)]);
  if (overview.status === 'fulfilled') store.set({ overview: overview.value });
  if (review.status === 'fulfilled') store.set({ review: review.value });
  setBusy(pane, false);
  renderWorkspace();

  const failed = [overview, review].find((result) => result.status === 'rejected');
  if (failed) showError(failed.reason);
  else {
    const report = store.get().overview?.verification;
    announce(dom['live-polite'], trustLine(report || {}, t).text);
  }
}

/** Render the document pane and the assistant panel. */
function renderWorkspace() {
  const state = store.get();
  if (!state.document) return;

  fill(
    dom['document-pane'],
    documentPane({ t, document: state.document, onClear: clearDocument }),
  );
  renderAssistant();
}

/** Render the assistant panel for the active tab. */
function renderAssistant() {
  const state = store.get();
  const deps = {
    t,
    language: state.language,
    clauseById: (id) => findClause(store.get(), id),
    onShow: showClause,
    onHelp: () => (location.hash = '#/help'),
  };

  const tablist = el('div', { className: 'tablist', attrs: { role: 'tablist', 'aria-label': t('nav.check') } });
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
  wireTabs(tablist, (tab) => {
    store.set({ tab });
    renderAssistant();
  });

  const panel = el('div', {
    id: 'tabpanel',
    attrs: { role: 'tabpanel', 'aria-labelledby': `tab-${state.tab}`, tabindex: '0' },
  });
  fill(panel, tabContent(state, deps));

  fill(dom['assistant-pane'], [
    rolePicker({
      t,
      roles: state.suggestedRoles.length ? state.suggestedRoles : ['other'],
      active: state.role,
      onChange: async (role) => {
        store.set({ role, overview: null, review: null });
        await loadAnalyses();
      },
    }),
    tablist,
    panel,
  ]);
}

/**
 * Build the content of the active tab.
 *
 * @param {object} state The current state.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The tab body.
 */
function tabContent(state, deps) {
  if (state.tab === 'overview') {
    return state.overview
      ? overviewView(state.overview, { ...deps, onCalendar: downloadCalendar })
      : loading();
  }
  if (state.tab === 'review') {
    return state.review
      ? el('div', { className: 'stack' }, [reviewView(state.review, deps), contextualHelp()])
      : loading();
  }
  if (state.tab === 'ask') {
    return askView({
      ...deps,
      answers: state.answers,
      suggested: checklist?.suggested_questions || [],
      busy: state.status.busy,
      onAsk: ask,
    });
  }
  if (state.tab === 'compare') {
    return compareView({ ...deps, state, onCompare: runCompare, samples });
  }
  return briefPanel(state, deps);
}

/**
 * Render the brief tab.
 *
 * @param {object} state The current state.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The brief, or an empty state.
 */
function briefPanel(state, deps) {
  const brief = buildBrief({
    document: state.document,
    overview: state.overview,
    review: state.review,
    answers: state.answers,
    lawReferences: state.lawReferences,
    checklist,
    role: state.role,
  });
  if (!isUseful(brief)) return loading();
  return briefView(brief, {
    ...deps,
    onPrint: () => window.print(),
    onExport: (format) => exportFile({ kind: 'brief', format, brief }),
  });
}

/** Render a loading placeholder. */
function loading() {
  return el('div', { className: 'stack-sm', attrs: { 'aria-busy': 'true' } }, [
    el('p', { className: 'source-note', text: t('app.loading') }),
    el('div', { className: 'skeleton', style: 'height:1.2em' }),
    el('div', { className: 'skeleton', style: 'height:1.2em;width:80%' }),
    el('div', { className: 'skeleton', style: 'height:1.2em;width:60%' }),
  ]);
}

/* --------------------------------------------------------------- actions */

/**
 * Ask a question about the document.
 *
 * @param {string} question What the user typed.
 */
async function ask(question) {
  await withBusy(t('app.loading'), async () => {
    const answer = await api.ask({
      ...analysisBody(store.get()),
      question,
      history: recentTurns(store.get().answers),
    });
    store.update((state) => answerReceived(state, answer));
    renderAssistant();
    announce(dom['live-polite'], trustLine(answer.verification, t).text);
  });
}

/**
 * Show a clause, highlighting a citation's quote and moving focus to it.
 *
 * @param {string} clauseId Which clause.
 * @param {object|null} citation The citation to highlight, if any.
 */
function showClause(clauseId, citation) {
  const state = store.get();
  const clause = findClause(state, clauseId);
  if (!clause) return;

  const narrow = window.matchMedia('(width < 60rem)').matches;
  if (narrow) {
    dom['clause-dialog-title'].textContent = clause.label
      ? t('clause.numbered', { label: clause.label })
      : clause.id;
    fill(dom['clause-dialog-body'], [
      clause.heading && el('strong', { text: clause.heading }),
      el('p', { style: 'white-space:pre-wrap', text: clause.text }),
    ]);
    openDialog(dom['clause-dialog']);
    return;
  }

  revealClause({
    container: document.getElementById('clause-list'),
    clauses: state.document.clauses,
    clauseId,
    citation,
    t,
    onBack: () => document.getElementById('tabpanel')?.focus(),
  });
}

/** Clear the document from the browser and from the server cache. */
async function clearDocument() {
  const state = store.get();
  if (!window.confirm(t('document.clearConfirm'))) return;
  if (state.document) await api.clearCache(state.document.id).catch(() => {});
  store.set({
    document: null, overview: null, review: null, compare: null,
    answers: [], lawReferences: [], view: 'upload',
  });
  checklist = null;
  dom.workspace.hidden = true;
  dom['upload-panel'].hidden = false;
  dom.main.focus();
}

/**
 * Download the key dates as a calendar file.
 *
 * @param {object[]} dates Absolute key dates.
 */
async function downloadCalendar(dates) {
  await withBusy(t('app.loading'), async () => {
    const file = await api.calendar({
      document_id: store.get().document.id,
      events: dates.map((date) => ({ title: date.title, date: date.date, description: date.description })),
    });
    saveBlob(file.blob, file.filename || downloadName('key-dates', 'ics'));
    announce(dom['live-polite'], t('a11y.fileReady', { format: 'Calendar' }));
  });
}

/**
 * Export something as Word or PDF.
 *
 * @param {object} payload The export request.
 */
async function exportFile(payload) {
  await withBusy(t('app.loading'), async () => {
    const file = await api.export({ ...payload, language: store.get().language });
    saveBlob(file.blob, file.filename || downloadName(payload.kind, payload.format));
    announce(dom['live-polite'], t('a11y.fileReady', { format: payload.format.toUpperCase() }));
  });
}

/**
 * Compare the open document with another.
 *
 * @param {object} request `{ mode, otherSampleId }`.
 */
async function runCompare(request) {
  await withBusy(t('app.loading'), async () => {
    const other = await api.sample(request.otherSampleId);
    const result = await api.compare({
      mode: request.mode,
      before: store.get().document,
      after: other.document,
      audience: analysisBody(store.get()).audience,
    });
    store.set({ compare: result });
    renderAssistant();
  });
}

/* ------------------------------------------------------------ other views */

/** Render the law lookup page. */
function renderLaws() {
  fill(
    dom['laws-pane'],
    lawsView({
      t,
      language: store.get().language,
      references: store.get().lawReferences,
      onLookup: (query) => api.lawLookup(query),
      onCompare: (payload) => api.lawCompare(payload),
      onBrowse: (kind) => api.lawChanges(kind),
      onExport: (payload) => exportFile({ kind: 'law_comparison', ...payload }),
      onError: showError,
    }),
  );
}

/** Render the letter drafting page. */
function renderDraft() {
  fill(
    dom['draft-pane'],
    draftView({
      t,
      language: store.get().language,
      state: store.get(),
      api,
      onExport: exportFile,
      onError: showError,
    }),
  );
}

/** Render the Get help page. */
async function renderHelp() {
  try {
    const resources = await api.resources();
    fill(dom['help-pane'], helpView(resources, { t, language: store.get().language }));
  } catch (error) {
    showError(error);
  }
}

/** Render the contextual "helpful next steps" strip. */
function contextualHelp() {
  const holder = el('div');
  const state = store.get();
  api
    .resources({ docType: state.document?.doc_type, situations: situations(state), contextual: true })
    .then((resources) => {
      const strip = helpStrip(resources, { t, language: state.language });
      if (strip) fill(holder, strip);
    })
    .catch(() => {});
  return holder;
}

/* ----------------------------------------------------------------- utils */

/**
 * Run an action with a busy state, announcing progress and reporting failures.
 *
 * @param {string} message What to announce while it runs.
 * @param {() => Promise<void>} action The work.
 */
async function withBusy(message, action) {
  store.set({ status: { busy: true, message }, error: null });
  announce(dom['live-polite'], message);
  setBusy(dom.main, true);
  try {
    await action();
  } catch (error) {
    showError(error);
  } finally {
    store.set({ status: { busy: false, message: '' } });
    setBusy(dom.main, false);
  }
}

/**
 * Show an error to the user and to screen readers.
 *
 * @param {Error} error What went wrong.
 */
function showError(error) {
  const message = error instanceof ApiError ? error.message : t('errors.generic');
  store.set({ error: message });
  announce(dom['live-alert'], message);
  const banner = el('div', { className: 'notice notice--error', attrs: { role: 'alert' } }, [
    el('div', {}, [el('strong', { text: t('errors.summaryTitle') }), el('p', { style: 'margin:0', text: message })]),
  ]);
  const host = dom.workspace.hidden ? dom['upload-controls'] : dom['assistant-pane'];
  host.prepend(banner);
}

/**
 * Show a plain message without treating it as an error.
 *
 * @param {string} message What to say.
 */
function showMessage(message) {
  announce(dom['live-alert'], message);
}

/**
 * Save a blob to the viewer's device.
 *
 * @param {Blob} blob The file.
 * @param {string} filename What to call it.
 */
function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = el('a', { attrs: { href: url, download: filename }, className: 'sr-only' });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), prefersReducedMotion() ? 0 : 1000);
}

/**
 * Read a value from local storage, tolerating private browsing.
 *
 * @param {string} key The key.
 * @returns {string|null} The value, or null.
 */
function safeRead(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/**
 * Write a value to local storage, tolerating private browsing.
 *
 * @param {string} key The key.
 * @param {string} value The value.
 */
function safeWrite(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage is a convenience here; the app works the same without it.
  }
}

start();
