/**
 * Drafting a letter from facts the user has confirmed.
 *
 * The rule the whole page is built around: the model may suggest wording, never
 * a fact. Every value in the letter comes from this form, download stays
 * disabled until the user confirms the facts, and a prefilled value shows the
 * clause it came from.
 */

import { el, fill, icon } from '../dom.js';

const TYPE_INPUTS = {
  text: 'text',
  date: 'date',
  money: 'text',
  address: 'text',
  email: 'email',
  phone: 'tel',
  clause_ref: 'text',
};

/**
 * Render the drafting page.
 *
 * @param {object} deps `{ t, state, api, onExport, onError }`.
 * @returns {HTMLElement} The page.
 */
export function draftView(deps) {
  const { t } = deps;
  const host = el('div', { className: 'stack' });

  deps.api
    .draftTemplates()
    .then((templates) => fill(host, picker(templates, deps)))
    .catch(deps.onError);

  return el('div', { className: 'stack' }, [
    el('p', { className: 'prose', text: t('draft.intro') }),
    host,
  ]);
}

/**
 * Render the template chooser.
 *
 * @param {object[]} templates Available templates.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The chooser and the editor beneath it.
 */
function picker(templates, deps) {
  const { t } = deps;
  const editor = el('div', { className: 'stack' });

  const select = el(
    'select',
    {
      id: 'template-select',
      onchange: (event) => openTemplate(event.target.value, templates, editor, deps),
    },
    [
      el('option', { attrs: { value: '' }, text: '—' }),
      ...templates.map((template) => el('option', { attrs: { value: template.id }, text: template.title })),
    ],
  );

  return el('div', { className: 'stack' }, [
    el('div', { className: 'card field' }, [
      el('label', { attrs: { for: 'template-select' }, text: t('draft.chooseTemplate') }),
      select,
    ]),
    editor,
  ]);
}

/**
 * Open one template: build its facts sheet and its live preview.
 *
 * @param {string} templateId Which template.
 * @param {object[]} templates All templates.
 * @param {HTMLElement} host Where to render.
 * @param {object} deps Render dependencies.
 */
async function openTemplate(templateId, templates, host, deps) {
  const { t, state } = deps;
  if (!templateId) return fill(host, []);

  const template = templates.find((entry) => entry.id === templateId);
  if (!template) return fill(host, []);

  let prefill = {};
  if (state.document) {
    prefill = await deps.api
      .draftPrefill({
        template_id: templateId,
        document: state.document,
        overview: state.overview,
      })
      .catch(() => ({ values: {} }));
  }

  const facts = { ...(prefill.values || {}) };
  const sources = prefill.sources || {};
  const preview = el('div', { className: 'document', id: 'draft-preview' });
  const errors = el('div', { attrs: { role: 'alert' } });
  let confirmed = false;

  const refresh = debounce(async () => {
    try {
      const result = await deps.api.draftPreview({
        template_id: templateId,
        facts,
        language: deps.language,
      });
      fill(preview, renderBlocks(result.document || { blocks: [] }));
      fill(
        errors,
        result.wording_rejected
          ? el('div', { className: 'notice notice--warning' }, [
              icon('medium'),
              el('span', { text: t('draft.wordingRejected') }),
            ])
          : [],
      );
    } catch (error) {
      if (error.status === 422) fill(errors, fieldErrors(error, t));
      else deps.onError(error);
    }
  }, 350);

  const downloads = el('div', { className: 'row' });

  const setDownloads = () => {
    fill(
      downloads,
      ['docx', 'pdf'].map((format) =>
        el('button', {
          type: 'button',
          className: 'btn btn--primary',
          text: format === 'docx' ? t('draft.downloadWord') : t('draft.downloadPdf'),
          attrs: { disabled: !confirmed },
          onclick: () =>
            deps.onExport({ kind: 'draft', format, template_id: templateId, facts }),
        }),
      ),
    );
  };

  const form = el('form', { className: 'stack-sm', onsubmit: (event) => event.preventDefault() });
  for (const field of template.fields || []) {
    form.append(fieldControl(field, facts, sources, deps, refresh));
  }

  const confirmId = 'confirm-facts';
  form.append(
    el('div', { className: 'field' }, [
      el('div', { className: 'row' }, [
        el('input', {
          type: 'checkbox',
          id: confirmId,
          style: 'inline-size:auto;min-block-size:auto',
          onchange: (event) => {
            confirmed = event.target.checked;
            setDownloads();
          },
        }),
        el('label', { attrs: { for: confirmId }, text: t('draft.confirmLabel') }),
      ]),
      el('p', { className: 'field-hint', text: t('draft.confirmHint') }),
    ]),
  );

  setDownloads();
  refresh();

  fill(host, [
    el('div', { className: 'notice notice--warning' }, [
      icon('medium'),
      el('span', { text: t('draft.reviewBeforeSending') }),
    ]),
    el('div', { className: 'desk' }, [
      el('section', { className: 'card', attrs: { 'aria-labelledby': 'facts-heading' } }, [
        el('h2', { id: 'facts-heading', text: t('draft.facts') }),
        errors,
        form,
      ]),
      el('section', { className: 'stack-sm', attrs: { 'aria-labelledby': 'preview-heading' } }, [
        el('h2', { id: 'preview-heading', text: t('draft.preview') }),
        preview,
        downloads,
      ]),
    ]),
  ]);
}

/**
 * Render one fact field.
 *
 * @param {object} field The field schema.
 * @param {object} facts The facts being edited, mutated in place.
 * @param {object} sources Where prefilled values came from.
 * @param {object} deps Render dependencies.
 * @param {() => void} refresh Called when a value changes.
 * @returns {HTMLElement} The field.
 */
function fieldControl(field, facts, sources, { t, language }, refresh) {
  const id = `fact-${field.name}`;
  const label = field.labels?.[language] || field.labels?.en || field.name;
  const hint = field.help?.[language] || field.help?.en || '';
  const source = sources[field.name];

  const onInput = (event) => {
    facts[field.name] = event.target.value;
    refresh();
  };

  const common = {
    id,
    attrs: {
      name: field.name,
      maxlength: field.max_length ? String(field.max_length) : null,
      required: field.required || null,
      'aria-describedby': hint || source ? `${id}-hint` : null,
    },
    oninput: onInput,
  };

  let control;
  if (field.type === 'multiline') {
    control = el('textarea', common);
    control.value = facts[field.name] || '';
  } else if (field.type === 'choice') {
    control = el(
      'select',
      { ...common, onchange: onInput },
      (field.choices || []).map((choice) =>
        el('option', { attrs: { value: choice, selected: facts[field.name] === choice }, text: choice }),
      ),
    );
  } else {
    control = el('input', { ...common, type: TYPE_INPUTS[field.type] || 'text' });
    control.value = facts[field.name] || '';
  }

  return el('div', { className: 'field' }, [
    el('label', { attrs: { for: id }, text: label }),
    control,
    (hint || source) &&
      el('p', { id: `${id}-hint`, className: 'field-hint' }, [
        hint,
        source && el('span', { className: 'chip', text: t('draft.fromClause', { label: source.label }) }),
      ]),
  ]);
}

/**
 * Render an error summary that links to each invalid field.
 *
 * @param {object} error An `ApiError` with field details.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The summary.
 */
function fieldErrors(error, t) {
  return el('div', { className: 'notice notice--error' }, [
    el('div', {}, [
      el('strong', { text: t('errors.summaryTitle') }),
      el(
        'ul',
        { style: 'margin:0.5rem 0 0' },
        (error.fields || []).map((entry) =>
          el('li', {}, [
            el('a', { attrs: { href: `#fact-${entry.field}` }, text: `${entry.field}: ${entry.message}` }),
          ]),
        ),
      ),
    ]),
  ]);
}

/**
 * Render a document model as HTML.
 *
 * The same model produces the Word file and the PDF, so what is previewed here
 * is what downloads.
 *
 * @param {object} model A `DocumentModel`.
 * @returns {Node[]} The rendered blocks.
 */
export function renderBlocks(model) {
  return (model.blocks || []).map((block) => {
    if (block.type === 'heading') return el(`h${Math.min(block.level || 2, 4)}`, { text: inlineText(block) });
    if (block.type === 'list') {
      return el(
        block.ordered ? 'ol' : 'ul',
        {},
        (block.items || []).map((item) => el('li', { text: item })),
      );
    }
    if (block.type === 'quote') return el('blockquote', {}, [el('p', { text: inlineText(block) })]);
    return el('p', {}, inlineNodes(block));
  });
}

/**
 * Flatten a block's runs into plain text.
 *
 * @param {object} block A block.
 * @returns {string} The text.
 */
function inlineText(block) {
  return (block.runs || []).map((run) => run.text).join('');
}

/**
 * Render a block's runs, marking the ones that came from a confirmed fact.
 *
 * @param {object} block A block.
 * @returns {Node[]} The nodes.
 */
function inlineNodes(block) {
  return (block.runs || []).map((run) => {
    if (run.fact) {
      return el('span', {
        style: 'text-decoration:underline dotted var(--seal);text-underline-offset:0.2em',
        text: run.text,
      });
    }
    if (run.bold) return el('strong', { text: run.text });
    if (run.italic) return el('em', { text: run.text });
    return document.createTextNode(run.text);
  });
}

/**
 * Delay a function until calls stop arriving.
 *
 * @param {Function} fn What to call.
 * @param {number} wait Milliseconds of quiet before calling.
 * @returns {Function} The debounced function.
 */
function debounce(fn, wait) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), wait);
  };
}
