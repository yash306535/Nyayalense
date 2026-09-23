/**
 * The legal assistant page: one place to ask, with a choice of what to ask.
 *
 * Three modes share the page, the way a mode picker sits above a chat input:
 * comparing a section or topic across the old and new codes, a general legal
 * question answered from packaged statute text, and questions about whatever
 * document is currently open. Nothing here changes how any of the three are
 * answered -- each is the same verified result the rest of the product shows,
 * only reachable from one page instead of three.
 */

import { el, icon, srOnly } from '../dom.js';
import { askView } from './ask.js';
import { lawsView } from './laws.js';
import { legalQaView } from './legal_qa.js';

export const MODES = ['compare', 'legal_qa', 'document_qa'];

/**
 * Render the assistant page.
 *
 * @param {object} deps `{ t, mode, onModeChange, compare, legalQa, documentQa }`.
 *   `compare` and `legalQa` are the dependency objects `lawsView` and
 *   `legalQaView` each expect. `documentQa` is `{ hasDocument, ...askDeps }`,
 *   where `askDeps` is what `askView` expects.
 * @returns {HTMLElement} The page.
 */
export function assistantView(deps) {
  const { t, mode } = deps;
  return el('div', { className: 'stack' }, [
    el('p', { className: 'prose', text: t('assistant.subtitle') }),
    modePicker(deps),
    el('div', { className: 'stack', id: 'assistant-mode-content' }, [modeContent(mode, deps)]),
  ]);
}

/**
 * Render the three-way mode picker.
 *
 * Built on the same radio-group pattern as the reading-level toggle, so a
 * screen reader announces it the same way and it needs no new keyboard
 * handling: arrow keys already move between radio options.
 *
 * @param {object} deps `{ t, mode, onModeChange }`.
 * @returns {HTMLElement} The picker.
 */
function modePicker(deps) {
  const { t, mode, onModeChange } = deps;
  const group = el('div', {
    className: 'filter-group',
    attrs: { role: 'radiogroup', 'aria-labelledby': 'assistant-mode-label' },
  });

  for (const candidate of MODES) {
    const id = `assistant-mode-${candidate}`;
    group.append(
      el('input', {
        type: 'radio',
        id,
        attrs: { name: 'assistant-mode', value: candidate, checked: candidate === mode },
        onchange: () => onModeChange(candidate),
      }),
      el('label', { attrs: { for: id } }, [
        el('span', { text: t(`assistant.mode${camel(candidate)}`) }),
        el('span', { className: 'mode-picker__hint', text: t(`assistant.mode${camel(candidate)}Hint`) }),
      ]),
    );
  }

  const label = srOnly(t('assistant.heading'));
  label.id = 'assistant-mode-label';
  return el('div', { className: 'mode-picker' }, [label, group]);
}

/**
 * Turn `document_qa` into `DocumentQa`, to match the translation keys.
 *
 * @param {string} mode One of {@link MODES}.
 * @returns {string} The key fragment.
 */
function camel(mode) {
  return mode.replace(/(?:^|_)([a-z])/g, (_, letter) => letter.toUpperCase());
}

/**
 * Render whichever mode is active.
 *
 * @param {string} mode One of {@link MODES}.
 * @param {object} deps See {@link assistantView}.
 * @returns {HTMLElement} That mode's content.
 */
function modeContent(mode, deps) {
  if (mode === 'legal_qa') return legalQaView(deps.legalQa);
  if (mode === 'document_qa') return documentQaContent(deps);
  return lawsView(deps.compare);
}

/**
 * Render the document Q&A mode: the usual ask panel once a document is open,
 * otherwise a prompt to go open one.
 *
 * @param {object} deps See {@link assistantView}.
 * @returns {HTMLElement} The content.
 */
function documentQaContent(deps) {
  const { t, documentQa } = deps;
  if (documentQa.hasDocument) return askView(documentQa);
  return el('div', { className: 'card stack-sm' }, [
    el('div', { className: 'notice' }, [icon('question'), el('span', { text: t('assistant.noDocument') })]),
    el('a', { className: 'btn btn--primary', attrs: { href: '#/check' }, text: t('assistant.noDocumentCta') }),
  ]);
}
