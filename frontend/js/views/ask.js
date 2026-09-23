/**
 * Asking questions about the document.
 *
 * The interesting state is `not_found`: the document simply does not answer.
 * That is shown as a first-class result with a question to put to the other
 * party, rather than dressed up as an answer.
 */

import { el, icon } from '../dom.js';
import { questionPrompt, statements, trustBlock } from './evidence.js';

/**
 * Render the ask panel.
 *
 * @param {object} deps `{ t, answers, suggested, busy, onAsk, clauseById, onShow, idPrefix }`.
 *   `idPrefix` keeps element ids unique when the panel is rendered more than
 *   once on the page at a time, such as from the legal assistant's "ask about
 *   my document" mode alongside the check workspace's own ask tab. Empty by
 *   default, for the one-panel case.
 * @returns {HTMLElement} The panel.
 */
export function askView(deps) {
  const { t, answers, suggested, onAsk, idPrefix = '' } = deps;
  const inputId = `${idPrefix}question-input`;
  const hintId = `${idPrefix}ask-hint`;

  const input = el('input', {
    type: 'text',
    id: inputId,
    attrs: { placeholder: t('ask.placeholder'), maxlength: '1000', 'aria-describedby': hintId },
  });

  const button = el('button', {
    type: 'submit',
    className: 'btn btn--primary',
    text: t('ask.submit'),
  });

  // Pending state is local to this form. Reading a global busy flag would leave
  // the button disabled after an unrelated action finished.
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
    el('form', {
      className: 'stack-sm',
      onsubmit: (event) => {
        event.preventDefault();
        submit();
      },
    }, [
      el('div', { className: 'field' }, [
        el('label', { attrs: { for: inputId }, text: t('ask.label') }),
        input,
        el('p', { id: hintId, className: 'field-hint', text: t('ask.emptyState') }),
      ]),
      button,
    ]),
    suggested?.length > 0 && suggestedQuestions(suggested, t, onAsk),
    el(
      'div',
      { className: 'stack', id: `${idPrefix}answers` },
      [...answers].reverse().map((answer) => answerCard(answer, deps)),
    ),
  ]);
}

/**
 * Render the suggested questions for this document type.
 *
 * @param {string[]} suggested The questions.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @param {(question: string) => void} onAsk Ask handler.
 * @returns {HTMLElement} The list.
 */
function suggestedQuestions(suggested, t, onAsk) {
  return el('div', { className: 'stack-sm' }, [
    el('p', { className: 'field-hint flush', text: t('ask.suggested') }),
    el(
      'div',
      { className: 'row' },
      suggested.map((question) =>
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
 * Render one answer.
 *
 * @param {object} answer The `/qa` result.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The answer card.
 */
function answerCard(answer, deps) {
  const { t } = deps;
  const answered = answer.answer_type === 'direct' || answer.answer_type === 'interpretation';

  return el('article', { className: 'panel' }, [
    el('div', { className: 'panel__header' }, [
      el('p', { className: 'flush-strong', text: answer.question }),
    ]),
    el('div', { className: 'panel__body stack-sm' }, [
      trustBlock(answer.verification, t),
      answered
        ? statements(answer.statements, deps)
        : el('p', {
            className: 'empty-cell',
            text: answer.answer_type === 'out_of_scope' ? t('ask.outOfScope') : t('ask.notFound'),
          }),
      answer.suggested_question_to_other_party &&
        questionPrompt(answer.suggested_question_to_other_party, t('ask.askInstead')),
      answer.related_clause_ids?.length > 0 && relatedClauses(answer.related_clause_ids, deps),
      answer.needs_professional && professionalNote(answer, t),
    ]),
  ]);
}

/**
 * Render links to the closest related clauses.
 *
 * @param {string[]} clauseIds The clause ids.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The row of links.
 */
function relatedClauses(clauseIds, deps) {
  const { t, clauseById, onShow } = deps;
  return el('div', { className: 'row' }, [
    el('span', { className: 'source-note', text: `${t('ask.relatedClauses')}:` }),
    ...clauseIds.map((clauseId) =>
      el('button', {
        type: 'button',
        className: 'btn btn--small btn--quiet',
        text: clauseById(clauseId)?.label || clauseId,
        onclick: () => onShow(clauseId, null),
      }),
    ),
  ]);
}

/**
 * Render the note shown when a question needs legal judgement.
 *
 * @param {object} answer The answer.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The note.
 */
function professionalNote(answer, t) {
  return el('div', { className: 'notice notice--warning' }, [
    icon('medium'),
    el('div', {}, [
      el('strong', { text: t('ask.needsProfessional') }),
      answer.questions_for_professional?.length > 0 &&
        el('div', {}, [
          el('p', { className: 'label-gap', text: t('ask.questionsForLawyer') }),
          el(
            'ul',
            { className: 'flush' },
            answer.questions_for_professional.map((question) => el('li', { text: question })),
          ),
        ]),
    ]),
  ]);
}
