/**
 * What the controller and the actions both need.
 *
 * The application is one page with one document open at a time, so this is a
 * module-level singleton by design rather than by accident. Keeping it here
 * lets the boot code and the document actions be read separately.
 */

import { announce, setBusy } from './a11y.js';
import { ApiError } from './api.js';
import { el } from './dom.js';
import { createStore } from './state.js';

/** The observable application state. */
export const store = createStore();

/** Elements the controller touches, cached once at boot. */
export const dom = {};

const DOM_IDS = [
  'live-polite', 'live-alert', 'demo-badge', 'language-select', 'theme-toggle',
  'upload-panel', 'upload-controls', 'workspace', 'document-pane', 'assistant-pane',
  'laws-pane', 'draft-pane', 'help-pane', 'about-pane', 'clause-dialog',
  'clause-dialog-title', 'clause-dialog-body', 'main',
];

let translate = (key) => key;
let samples = [];
let checklist = null;
let glossary = [];

/** Look up every element the controller uses. */
export function cacheDom() {
  for (const id of DOM_IDS) dom[id] = document.getElementById(id);
}

/**
 * Translate a key in the current language.
 *
 * A function rather than a bound translator, so callers always get the current
 * language rather than whichever one was active when they were created.
 *
 * @param {string} key A dotted key.
 * @param {object} [values] Placeholder values.
 * @returns {string} The translated string.
 */
export function t(key, values) {
  return translate(key, values);
}

/**
 * Install a translator for the chosen language.
 *
 * @param {(key: string, values?: object) => string} translator The translator.
 */
export function setTranslator(translator) {
  translate = translator;
}

/** @returns {object[]} The built-in samples. */
export function getSamples() {
  return samples;
}

/**
 * Record the built-in samples.
 *
 * @param {object[]} list What the API returned.
 */
export function setSamples(list) {
  samples = list;
}

/** @returns {object|null} The checklist for the open document, if loaded. */
export function getChecklist() {
  return checklist;
}

/**
 * Record the checklist for the open document.
 *
 * @param {object|null} value The checklist, or null.
 */
export function setChecklist(value) {
  checklist = value;
}

/** @returns {object[]} The packaged glossary entries. */
export function getGlossary() {
  return glossary;
}

/**
 * Record the packaged glossary entries.
 *
 * @param {object[]} entries What the API returned.
 */
export function setGlossary(entries) {
  glossary = entries;
}

/**
 * Run an action with a busy state, announcing progress and reporting failures.
 *
 * @param {string} message What to announce while it runs.
 * @param {() => Promise<void>} action The work.
 */
export async function withBusy(message, action) {
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
 * Show an error to the reader and to assistive technology.
 *
 * @param {Error} error What went wrong.
 */
export function showError(error) {
  const message = error instanceof ApiError ? error.message : t('errors.generic');
  store.set({ error: message });
  announce(dom['live-alert'], message);

  const host = dom.workspace.hidden ? dom['upload-controls'] : dom['assistant-pane'];
  host.prepend(
    el('div', { className: 'notice notice--error', attrs: { role: 'alert' } }, [
      el('div', {}, [
        el('strong', { text: t('errors.summaryTitle') }),
        el('p', { className: 'flush', text: message }),
      ]),
    ]),
  );
}

/**
 * Announce something in the polite live region.
 *
 * @param {string} message What to say.
 */
export function announcePolite(message) {
  announce(dom['live-polite'], message);
}

/**
 * Announce something in the assertive region.
 *
 * @param {string} message What to say.
 */
export function announceAlert(message) {
  announce(dom['live-alert'], message);
}
