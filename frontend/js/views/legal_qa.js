/**
 * A general legal question, answered from packaged, reviewed statute text.
 *
 * The interesting case is the same as document Q&A: `not_found` is a first-
 * class result, shown plainly rather than dressed up as an answer. There is no
 * document behind this, so every citation is shown inline as its own quote
 * rather than pointing at a clause the reader can open.
 */

import { el, icon } from '../dom.js';
import { trustBlock } from './evidence.js';

const SUGGESTION_COUNT = 4;

/**
 * Render the general legal Q&A panel.
 *
 * @param {object} deps `{ t, answers, onAsk }`. `answers` is the conversation
 *   so far, oldest first; `onAsk` sends one question and resolves once the
 *   store holds the answer.
 * @returns {HTMLElement} The panel.
 */
export function legalQaView(deps) {
  const { t, answers, onAsk } = deps;

  const input = el('input', {
    type: 'text',
    id: 'legal-qa-input',
    attrs: {
      placeholder: t('legalQa.placeholder'),
      maxlength: '1000',
      'aria-describedby': 'legal-qa-hint',
    },
  });

  const button = el('button', {
    type: 'submit',
    className: 'btn btn--primary',
    text: t('legalQa.submit'),
  });

  const submit = async () => {
    const question = input.value.trim();
    if (!question || button.disabled) return;
    input.value = '';
    button.disabled = true;
    try {
      await onAsk(question);
    } finally {
      button.disabled = false;
    }
  };

  return el('div', { className: 'stack' }, [
    el('p', { className: 'field-hint', text: t('legalQa.disclaimer') }),
    el(
      'form',
      {
        className: 'stack-sm',
        onsubmit: (event) => {
          event.preventDefault();
          submit();
        },
      },
      [
        el('div', { className: 'field' }, [
          el('label', { attrs: { for: 'legal-qa-input' }, text: t('legalQa.label') }),
          input,
          el('p', { id: 'legal-qa-hint', className: 'field-hint', text: t('legalQa.emptyState') }),
        ]),
        button,
      ],
    ),
    answers.length === 0 && suggestedQuestions(t, submitQuestion(input, onAsk)),
    el(
      'div',
      { className: 'chat-thread', id: 'legal-qa-thread', attrs: { 'aria-live': 'polite' } },
      [...answers].reverse().map((entry) => turnCard(entry, t)),
    ),
  ]);
}

/**
 * Build a handler that asks a suggested question directly.
 *
 * @param {HTMLInputElement} input The question field, cleared once asked.
 * @param {(question: string) => Promise<void>} onAsk Ask handler.
 * @returns {(question: string) => void} The click handler.
 */
function submitQuestion(input, onAsk) {
  return (question) => {
    input.value = '';
    onAsk(question);
  };
}

/**
 * Render the starting suggestions, shown before the first question.
 *
 * @param {(key: string, values?: object) => string} t Translation function.
 * @param {(question: string) => void} onAsk Ask handler.
 * @returns {HTMLElement} The suggestions.
 */
function suggestedQuestions(t, onAsk) {
  const questions = Array.from({ length: SUGGESTION_COUNT }, (_, index) =>
    t(`legalQa.suggestion${index + 1}`),
  );
  return el('div', { className: 'stack-sm' }, [
    el('p', { className: 'field-hint flush', text: t('ask.suggested') }),
    el(
      'div',
      { className: 'row' },
      questions.map((question) =>
        el('button', {
          type: 'button',
          className: 'btn btn--small',
          text: question,
          onclick: () => onAsk(question),
        }),
      ),
    ),
  ]);
}

/**
 * Render one question-and-answer turn.
 *
 * @param {object} entry `{ question, matched, answer }`, the `/laws/qa` result.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The turn.
 */
function turnCard(entry, t) {
  const { question, matched, answer } = entry;
  const answered = answer.answer_type === 'direct' || answer.answer_type === 'interpretation';

  return el('article', { className: 'stack-sm' }, [
    el('p', { className: 'chat-turn__question' }, [question]),
    el('div', { className: 'chat-turn__answer stack-sm' }, [
      matched?.length > 0 && matchedSections(matched, t),
      trustBlock(answer.verification, t),
      answered
        ? el(
            'div',
            { className: 'stack-sm' },
            answer.statements.map((statement) => legalStatement(statement, t)),
          )
        : el('p', {
            className: 'empty-cell',
            text: answer.answer_type === 'out_of_scope' ? t('legalQa.outOfScope') : t('legalQa.notFound'),
          }),
      answer.needs_professional &&
        el('p', { className: 'notice notice--warning' }, [
          icon('medium'),
          el('span', { text: t('ask.needsProfessional') }),
        ]),
    ]),
  ]);
}

/**
 * Render the chips naming which sections the answer was allowed to draw from.
 *
 * @param {object[]} matched Provision references.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The chip row.
 */
function matchedSections(matched, t) {
  return el('div', { className: 'stack-sm' }, [
    el('p', { className: 'field-hint flush', text: t('legalQa.matchedSections') }),
    el(
      'div',
      { className: 'row' },
      matched.map((reference) =>
        el('span', {
          className: 'chip',
          text: `${reference.act.toUpperCase()} ${reference.section}`,
        }),
      ),
    ),
  ]);
}

/**
 * Render one statement with its citations shown as inline quotes.
 *
 * There is no document view to point a seal at here, so a verified citation is
 * its own small quote block, headed by the section it names.
 *
 * @param {object} statement A verified statement.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The statement block.
 */
function legalStatement(statement, t) {
  const verified = (statement.citations || []).filter((citation) => citation.verified);
  return el('div', { className: 'statement' }, [
    el('p', { className: 'statement__text', text: statement.text }),
    statement.kind === 'interpretation' &&
      el('p', { className: 'source-note', text: t('ask.interpretation') }),
    verified.length > 0 &&
      el(
        'div',
        { className: 'stack-sm' },
        verified.map((citation) =>
          el('blockquote', { className: 'quote-block' }, [
            el('p', { text: citation.quote }),
            el('cite', { text: sectionLabel(citation.clause_id) }),
          ]),
        ),
      ),
  ]);
}

/**
 * Turn a synthetic clause id such as ``IPC-420`` back into ``IPC 420``.
 *
 * @param {string} clauseId The citation's clause id.
 * @returns {string} A readable section reference.
 */
function sectionLabel(clauseId) {
  return clauseId.replace('-', ' ');
}
