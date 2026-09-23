/**
 * What happens when the reader does something.
 *
 * The views never call the API. They call one of these, and each one updates
 * the store, re-renders and announces the result.
 */

import { openDialog, setBusy } from './a11y.js';
import { api } from './api.js';
import { saveBlob } from './browser.js';
import { el, fill } from './dom.js';
import { downloadName, trustLine } from './format.js';
import {
  announcePolite,
  dom,
  getChecklist,
  getSamples,
  setChecklist,
  showError,
  store,
  t,
  withBusy,
} from './session.js';
import {
  analysisBody,
  answerReceived,
  documentLoaded,
  findClause,
  recentTurns,
  situations,
} from './state.js';
import { pendingHelpStrip, renderAssistant, renderWorkspace } from './workspace.js';
import { revealClause } from './views/document.js';

const NARROW = '(width < 60rem)';

/**
 * The callbacks the workspace and its views invoke.
 *
 * @returns {object} The action bundle.
 */
export function actions() {
  return {
    t,
    onClear: clearDocument,
    onShowClause: showClause,
    onHelp: () => (location.hash = '#/help'),
    onSelectTab: (tab) => {
      store.set({ tab });
      renderAssistant(dom, store.get(), actions());
    },
    onChangeRole: async (role) => {
      store.set({ role, overview: null, review: null });
      await loadAnalyses();
    },
    onAsk: ask,
    onCalendar: downloadCalendar,
    onCompare: runCompare,
    onExportBrief: (format, brief) => exportFile({ kind: 'brief', format, brief }),
    onExportComparison: ({ format, comparison }) =>
      exportFile({ kind: 'comparison', format, comparison }),
    samples: getSamples,
    checklist: getChecklist,
    suggestedQuestions: () => getChecklist()?.suggested_questions || [],
    contextualHelp,
  };
}

/**
 * Ingest a document, then load its analyses.
 *
 * @param {() => Promise<object>} call The API call that produces the document.
 * @param {(doc: object|null) => void} setHeading Keeps the view heading accurate.
 */
export async function ingest(call, setHeading) {
  await withBusy(t('a11y.reading'), async () => {
    const result = await call();
    store.update((state) => documentLoaded(state, result));
    setChecklist(await api.checklist(result.document.doc_type).catch(() => null));

    dom['upload-panel'].hidden = true;
    dom.workspace.hidden = false;
    setHeading(result.document);
    renderWorkspace(dom, store.get(), actions());
    await loadAnalyses();
  });
}

/** Load the overview and the review in parallel, rendering each as it lands. */
export async function loadAnalyses() {
  const body = analysisBody(store.get());
  setBusy(dom['assistant-pane'], true);

  const [overview, review] = await Promise.allSettled([api.overview(body), api.review(body)]);
  if (overview.status === 'fulfilled') store.set({ overview: overview.value });
  if (review.status === 'fulfilled') store.set({ review: review.value });

  setBusy(dom['assistant-pane'], false);
  renderWorkspace(dom, store.get(), actions());

  const failed = [overview, review].find((result) => result.status === 'rejected');
  if (failed) showError(failed.reason);
  else announcePolite(trustLine(store.get().overview?.verification || {}, t).text);
}

/**
 * Ask a question about the document.
 *
 * @param {string} question What the reader typed.
 */
async function ask(question) {
  await withBusy(t('app.loading'), async () => {
    const answer = await api.ask({
      ...analysisBody(store.get()),
      question,
      history: recentTurns(store.get().answers),
    });
    store.update((state) => answerReceived(state, answer));
    renderAssistant(dom, store.get(), actions());
    announcePolite(trustLine(answer.verification, t).text);
  });
}

/**
 * Show a clause, highlighting a citation's quote and moving focus to it.
 *
 * On a narrow screen there is only one column, so the clause opens in a dialog
 * rather than scrolling the reader away from the answer.
 *
 * @param {string} clauseId Which clause.
 * @param {object|null} citation The citation to highlight, if any.
 */
function showClause(clauseId, citation) {
  const state = store.get();
  const clause = findClause(state, clauseId);
  if (!clause) return;

  if (window.matchMedia(NARROW).matches) {
    dom['clause-dialog-title'].textContent = clause.label
      ? t('clause.numbered', { label: clause.label })
      : clause.id;
    fill(dom['clause-dialog-body'], [
      clause.heading && el('strong', { text: clause.heading }),
      el('p', { className: 'preserve-breaks', text: clause.text }),
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

/**
 * Clear the document from the browser and from the server cache.
 *
 * @param {(doc: object|null) => void} [setHeading] Resets the view heading.
 */
async function clearDocument(setHeading) {
  const state = store.get();
  if (!window.confirm(t('document.clearConfirm'))) return;
  if (state.document) {
    await api.clearCache(state.document.id).catch(() => {
      // The cache expires on its own; failing to purge it early is not an error.
    });
  }

  store.set({
    document: null,
    overview: null,
    review: null,
    compare: null,
    answers: [],
    lawReferences: [],
    view: 'upload',
  });
  setChecklist(null);
  dom.workspace.hidden = true;
  dom['upload-panel'].hidden = false;
  if (typeof setHeading === 'function') setHeading(null);
  dom.main.focus();
}

/**
 * Download the key dates as a calendar file.
 *
 * @param {object[]} dates Dates the document states as calendar dates.
 */
async function downloadCalendar(dates) {
  await withBusy(t('app.loading'), async () => {
    const file = await api.calendar({
      document_id: store.get().document.id,
      events: dates.map(({ title, date, description }) => ({ title, date, description })),
    });
    saveBlob(file.blob, file.filename || downloadName('key-dates', 'ics'));
    announcePolite(t('a11y.fileReady', { format: 'Calendar' }));
  });
}

/**
 * Export something as Word or PDF.
 *
 * @param {object} payload What to export, and in which format.
 */
export async function exportFile(payload) {
  await withBusy(t('app.loading'), async () => {
    const state = store.get();
    const file = await api.export({
      ...payload,
      audience: { role: state.role, language: state.language, reading_level: state.readingLevel },
    });
    saveBlob(file.blob, file.filename || downloadName(payload.kind, payload.format));
    announcePolite(t('a11y.fileReady', { format: payload.format.toUpperCase() }));
  });
}

/**
 * Compare the open document with another.
 *
 * @param {{mode: string, otherSampleId: string}} request What to compare with.
 */
async function runCompare(request) {
  await withBusy(t('app.loading'), async () => {
    const other = await api.sample(request.otherSampleId);
    store.set({
      compare: await api.compare({
        mode: request.mode,
        before: store.get().document,
        after: other.document,
        audience: analysisBody(store.get()).audience,
      }),
    });
    renderAssistant(dom, store.get(), actions());
  });
}

/**
 * Build the contextual "helpful next steps" strip for the review tab.
 *
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} A holder that fills itself when the fetch lands.
 */
function contextualHelp(deps) {
  const state = store.get();
  return pendingHelpStrip(
    api.resources({
      docType: state.document?.doc_type,
      situations: situations(state),
      contextual: true,
    }),
    deps,
  );
}
