/**
 * "What if": what the document says about a situation.
 *
 * Consequences are reported only where the document itself states them. This
 * view never predicts an outcome, and says plainly when the document does not
 * cover the situation at all.
 */

import { el, icon } from '../dom.js';
import { statements, trustBlock } from './evidence.js';

/**
 * Render the what-if panel.
 *
 * @param {object} deps `{ t, presets, result, onRun, clauseById, onShow }`.
 * @returns {HTMLElement} The panel.
 */
export function scenariosView(deps) {
  const { t, presets, result, onRun } = deps;

  const input = el('input', {
    type: 'text',
    id: 'scenario-input',
    attrs: { placeholder: t('scenarios.placeholder'), maxlength: '500' },
  });

  const button = el('button', {
    type: 'submit',
    className: 'btn btn--primary',
    text: t('scenarios.run'),
  });

  const run = async (scenario) => {
    if (!scenario || button.disabled) return;
    button.disabled = true;
    try {
      await onRun(scenario);
    } finally {
      button.disabled = false;
    }
  };

  return el('div', { className: 'stack' }, [
    el('p', { className: 'field-hint', text: t('scenarios.intro') }),

    presets.length > 0 &&
      el('div', { className: 'stack-sm' }, [
        el('p', { className: 'field-hint flush', text: t('scenarios.presets') }),
        el(
          'div',
          { className: 'row' },
          presets.map((preset) =>
            el('button', {
              type: 'button',
              className: 'btn btn--small',
              text: preset.title,
              onclick: () => run(preset.title),
            }),
          ),
        ),
      ]),

    el('form', {
      className: 'stack-sm',
      onsubmit: (event) => {
        event.preventDefault();
        const value = input.value.trim();
        input.value = '';
        run(value);
      },
    }, [
      el('div', { className: 'field' }, [
        el('label', { attrs: { for: 'scenario-input' }, text: t('scenarios.label') }),
        input,
      ]),
      button,
    ]),

    result ? resultCard(result, deps) : el('p', { className: 'empty-state', text: t('scenarios.emptyState') }),
  ]);
}

/**
 * Render one what-if result.
 *
 * @param {object} result The `/scenarios` response.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The result card.
 */
function resultCard(result, deps) {
  const { t } = deps;
  return el('article', { className: 'panel' }, [
    el('div', { className: 'panel__header' }, [
      el('p', { className: 'flush-strong', text: result.scenario }),
    ]),
    el('div', { className: 'panel__body stack-sm' }, [
      trustBlock(result.verification, t),

      result.says?.length > 0
        ? section(t('scenarios.says'), statements(result.says, deps))
        : el('p', { className: 'empty-cell', text: t('scenarios.notCovered') }),

      result.consequences?.length > 0 &&
        section(t('scenarios.consequences'), statements(result.consequences, deps)),

      result.not_covered?.length > 0 &&
        section(
          t('scenarios.whatItDoesNotCover'),
          el('ul', {}, result.not_covered.map((line) => el('li', { text: line }))),
        ),

      result.next_steps?.length > 0 &&
        el('div', { className: 'notice' }, [
          icon('question'),
          el('div', {}, [
            el('strong', { text: t('scenarios.nextSteps') }),
            el('ul', { className: 'tight' }, result.next_steps.map((step) => el('li', { text: step }))),
          ]),
        ]),
    ]),
  ]);
}

/**
 * Wrap content under a small heading.
 *
 * @param {string} title The heading.
 * @param {HTMLElement} content The body.
 * @returns {HTMLElement} The section.
 */
function section(title, content) {
  return el('section', { className: 'stack-sm' }, [
    el('h2', { className: 'flush', text: title }),
    content,
  ]);
}
