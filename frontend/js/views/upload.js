/**
 * Getting a document in: drop zone, file picker, paste, or a built-in sample.
 *
 * The drop zone is also a real button, because drag and drop must never be the
 * only way to do something (WCAG 2.2, 2.5.7).
 */

import { el } from '../dom.js';

const ACCEPT = '.pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain';

/**
 * Render the upload panel.
 *
 * @param {object} deps `{ t, samples, demoMode, onFile, onPaste, onSample }`.
 * @returns {HTMLElement} The panel.
 */
export function uploadPanel({ t, samples, demoMode, onFile, onPaste, onSample }) {
  const input = el('input', {
    type: 'file',
    id: 'file-input',
    className: 'sr-only',
    attrs: { accept: ACCEPT },
    onchange: (event) => {
      const [file] = event.target.files || [];
      if (file) onFile(file);
      event.target.value = '';
    },
  });

  const zone = el('div', { className: 'dropzone' }, [
    el('p', { style: 'margin:0', text: t('upload.dropHere') }),
    el('p', { className: 'source-note', style: 'margin:0', text: t('upload.or') }),
    el('button', {
      type: 'button',
      className: 'btn btn--primary',
      text: t('upload.chooseFile'),
      onclick: () => input.click(),
    }),
    input,
  ]);

  wireDragAndDrop(zone, onFile);

  const textarea = el('textarea', {
    id: 'paste-text',
    attrs: { 'aria-describedby': 'paste-hint', rows: '8' },
  });

  const paste = el('details', { className: 'card' }, [
    el('summary', { text: t('upload.pasteInstead') }),
    el('div', { className: 'stack', style: 'margin-top:1rem' }, [
      el('div', { className: 'field' }, [
        el('label', { attrs: { for: 'paste-text' }, text: t('upload.pasteLabel') }),
        el('p', { id: 'paste-hint', className: 'field-hint', text: t('upload.pasteHint') }),
        textarea,
      ]),
      el('button', {
        type: 'button',
        className: 'btn btn--primary',
        text: t('upload.readIt'),
        onclick: () => onPaste(textarea.value),
      }),
    ]),
  ]);

  return el('div', { className: 'stack' }, [
    zone,
    paste,
    samplesPanel({ t, samples, onSample }),
    privacyNotice({ t, demoMode }),
  ]);
}

/**
 * Wire drag and drop onto the zone.
 *
 * @param {HTMLElement} zone The drop zone.
 * @param {(file: File) => void} onFile Called with the dropped file.
 */
function wireDragAndDrop(zone, onFile) {
  const stop = (event) => {
    event.preventDefault();
    event.stopPropagation();
  };
  zone.addEventListener('dragover', (event) => {
    stop(event);
    zone.classList.add('dropzone--over');
  });
  zone.addEventListener('dragleave', (event) => {
    stop(event);
    zone.classList.remove('dropzone--over');
  });
  zone.addEventListener('drop', (event) => {
    stop(event);
    zone.classList.remove('dropzone--over');
    const [file] = event.dataTransfer?.files || [];
    if (file) onFile(file);
  });
}

/**
 * Render the built-in samples.
 *
 * @param {object} deps `{ t, samples, onSample }`.
 * @returns {HTMLElement} The samples panel.
 */
function samplesPanel({ t, samples, onSample }) {
  return el('section', { className: 'card', attrs: { 'aria-labelledby': 'samples-heading' } }, [
    el('h2', { id: 'samples-heading', text: t('upload.trySample') }),
    el('p', { className: 'field-hint', text: t('upload.sampleHint') }),
    el(
      'ul',
      { className: 'register' },
      (samples || []).map((sample) =>
        el('li', {}, [
          el('span', { className: 'register__icon', text: '§' }),
          el('div', {}, [
            el('p', { className: 'register__name', text: sample.title }),
            el('p', { className: 'register__purpose', text: sample.description }),
          ]),
          el('div', { className: 'register__actions' }, [
            el('button', {
              type: 'button',
              className: 'btn',
              text: t('upload.readIt'),
              dataset: { sample: sample.id },
              onclick: () => onSample(sample.id),
            }),
          ]),
        ]),
      ),
    ),
  ]);
}

/**
 * Render the privacy notice shown before anything is sent.
 *
 * @param {object} deps `{ t, demoMode }`.
 * @returns {HTMLElement} The notice.
 */
function privacyNotice({ t, demoMode }) {
  return el('section', { className: 'notice notice--seal' }, [
    el('div', {}, [
      el('strong', { text: t('upload.privacyTitle') }),
      el('p', { style: 'margin:0.25rem 0 0', text: t('upload.privacyBody') }),
      demoMode && el('p', { style: 'margin:0.25rem 0 0', text: t('upload.privacyDemo') }),
    ]),
  ]);
}

/**
 * Render the role chooser shown once a document is loaded.
 *
 * Asked once, and only once, per document (WCAG 2.2, 3.3.7).
 *
 * @param {object} deps `{ t, roles, active, onChange }`.
 * @returns {HTMLElement} The chooser.
 */
export function rolePicker({ t, roles, active, onChange }) {
  const select = el(
    'select',
    {
      id: 'role-select',
      attrs: { 'aria-describedby': 'role-hint' },
      onchange: (event) => onChange(event.target.value),
    },
    roles.map((role) =>
      el('option', { attrs: { value: role, selected: role === active }, text: t(`roles.${role}`) }),
    ),
  );

  return el('div', { className: 'field' }, [
    el('label', { attrs: { for: 'role-select' }, text: t('upload.roleLabel') }),
    select,
    el('p', { id: 'role-hint', className: 'field-hint', text: t('upload.roleHint') }),
  ]);
}
