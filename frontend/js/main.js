/**
 * Application entry point.
 *
 * Boots the page, wires the header controls, and renders the view the URL
 * names. Everything that happens after a reader clicks something lives in
 * `actions.js`; everything drawn lives in `workspace.js` and `views/`.
 */

import { api } from './api.js';
import { applyTheme, readSetting, writeSetting } from './browser.js';
import { fill } from './dom.js';
import { initialLanguage, translator } from './i18n.js';
import { currentRoute, showRoute } from './router.js';
import {
  announceAlert,
  cacheDom,
  dom,
  setSamples,
  setTranslator,
  showError,
  store,
  t,
} from './session.js';
import { actions, exportFile, ingest } from './actions.js';
import { renderWorkspace } from './workspace.js';
import { aboutView } from './views/about.js';
import { draftView } from './views/draft.js';
import { helpView } from './views/help.js';
import { lawsView } from './views/laws.js';
import { uploadPanel } from './views/upload.js';

const SUPPORTED = ['en', 'hi', 'mr'];
const STORAGE_LANGUAGE = 'nyayalens.language';
const STORAGE_THEME = 'nyayalens.theme';

const bundles = {};

/** Start the application. */
async function start() {
  cacheDom();
  await loadLanguage(
    initialLanguage(SUPPORTED, readSetting(STORAGE_LANGUAGE), navigator.languages || []),
  );
  setTheme(readSetting(STORAGE_THEME));
  wireChrome();
  window.addEventListener('hashchange', route);

  try {
    const [meta, samples] = await Promise.all([api.meta(), api.samples()]);
    setSamples(samples);
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
 * English is always loaded too, so a gap in a translation shows as untranslated
 * text rather than a blank interface.
 *
 * @param {string} language One of the supported languages.
 */
async function loadLanguage(language) {
  if (!bundles[language]) bundles[language] = await (await fetch(`/i18n/${language}.json`)).json();
  if (!bundles.en) bundles.en = await (await fetch('/i18n/en.json')).json();

  setTranslator(translator(bundles, language));
  store.set({ language });
  document.documentElement.lang = language;
  writeSetting(STORAGE_LANGUAGE, language);

  for (const node of document.querySelectorAll('[data-i18n]')) {
    node.textContent = t(node.dataset.i18n);
  }
  document.title = `${t('app.name')} — ${t('app.tagline')}`;
}

/** Wire the header controls and the clause dialog. */
function wireChrome() {
  dom['language-select'].value = store.get().language;
  dom['language-select'].addEventListener('change', async (event) => {
    await loadLanguage(event.target.value);
    renderUpload();
    if (store.get().document) renderWorkspace(dom, store.get(), viewActions());
    route();
  });

  dom['theme-toggle'].addEventListener('click', () => {
    const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    setTheme(next);
    writeSetting(STORAGE_THEME, next);
  });

  for (const button of document.querySelectorAll('[data-close-dialog]')) {
    button.addEventListener('click', () => dom['clause-dialog'].close());
  }
}

/**
 * Apply a theme and keep the toggle's state in step with it.
 *
 * @param {string|null} theme `dark`, `light`, or null to follow the system.
 */
function setTheme(theme) {
  const dark = applyTheme(theme);
  dom['theme-toggle'].setAttribute('aria-pressed', String(dark));
  dom['theme-toggle'].textContent = dark ? t('app.lightMode') : t('app.darkMode');
}

/**
 * The action bundle, with the heading callback this module owns bound in.
 *
 * @returns {object} The actions the views invoke.
 */
function viewActions() {
  const bundle = actions();
  return { ...bundle, onClear: () => bundle.onClear(setCheckHeading) };
}

/** Show the view named by the URL fragment, and render it. */
function route() {
  const view = showRoute(currentRoute());
  ({ laws: renderLaws, draft: renderDraft, help: renderHelp, about: renderAbout })[view]?.();
}

/**
 * Keep the check view's heading accurate as it changes state.
 *
 * The heading stays in the DOM either way: a view with no level-one heading is
 * one a screen-reader user cannot orient themselves in.
 *
 * @param {object|null} doc The open document, or null on the upload screen.
 */
function setCheckHeading(doc) {
  const heading = document.getElementById('check-heading');
  if (heading) {
    heading.textContent = doc ? doc.title || t(`docTypes.${doc.doc_type}`) : t('upload.heading');
  }
}

/** Render the upload panel. */
function renderUpload() {
  fill(
    dom['upload-controls'],
    uploadPanel({
      t,
      samples: actions().samples(),
      demoMode: Boolean(store.get().meta?.demo_mode),
      onFile: (file) => beginIngest(() => api.upload(file)),
      onPaste: (text) =>
        text.trim()
          ? beginIngest(() => api.paste(text, t('document.title')))
          : announceAlert(t('errors.emptyText')),
      onSample: (id) => beginIngest(() => api.sample(id)),
    }),
  );
}

/**
 * Ingest a document and re-render the workspace around it.
 *
 * @param {() => Promise<object>} call The API call that produces the document.
 */
function beginIngest(call) {
  return ingest(call, setCheckHeading);
}

/** Render the law lookup page. */
function renderLaws() {
  fill(
    dom['laws-pane'],
    lawsView({
      t,
      language: store.get().language,
      references: store.get().lawReferences,
      onLookup: (query) => api.lawLookup(query),
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

/** Render the "How it works" page. */
function renderAbout() {
  fill(dom['about-pane'], aboutView({ t, meta: store.get().meta }));
}

start();
