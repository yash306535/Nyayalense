/**
 * Looking up an old criminal-law section and seeing what replaced it.
 *
 * Everything here is reference material read from packaged data. The page never
 * says which section applies to anyone's facts, and every row shows the source
 * it came from and whether a person has checked it.
 */

import { el, externalLink, icon } from '../dom.js';
import { comparisonTable, diffFragment } from './table.js';

/**
 * Render the law lookup page.
 *
 * @param {object} deps `{ t, references, onLookup, onCompare, onBrowse, onError, onExport }`.
 * @returns {HTMLElement} The page.
 */
export function lawsView(deps) {
  const { t } = deps;
  const results = el('div', { className: 'stack', id: 'law-results', attrs: { 'aria-live': 'polite' } });

  const input = el('input', {
    type: 'search',
    id: 'law-search',
    attrs: { placeholder: t('laws.searchPlaceholder'), 'aria-describedby': 'law-examples' },
  });

  const submit = async () => {
    const query = input.value.trim();
    if (!query) return;
    try {
      const found = await deps.onLookup(query);
      results.replaceChildren(lookupResult(found, deps));
    } catch (error) {
      deps.onError(error);
    }
  };

  return el('div', { className: 'stack' }, [
    el('p', { className: 'prose', text: t('laws.intro') }),
    el('div', { className: 'notice' }, [icon('question'), el('span', { text: t('laws.referenceOnly') })]),

    el('form', {
      className: 'card stack-sm',
      onsubmit: (event) => {
        event.preventDefault();
        submit();
      },
    }, [
      el('div', { className: 'field' }, [
        el('label', { attrs: { for: 'law-search' }, text: t('laws.searchLabel') }),
        input,
        el('p', { id: 'law-examples', className: 'field-hint', text: t('laws.examples') }),
      ]),
      el('button', { type: 'submit', className: 'btn btn--primary', text: t('laws.search') }),
    ]),

    deps.references?.length > 0 && foundInDocument(deps.references, deps),
    results,
    browseLists(deps),
  ]);
}

/**
 * Render the table of references detected in the open document.
 *
 * @param {object[]} references The detected references.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The section.
 */
function foundInDocument(references, deps) {
  const { t } = deps;
  return el('section', { className: 'stack-sm', attrs: { 'aria-labelledby': 'found-heading' } }, [
    el('h2', { id: 'found-heading', text: t('laws.foundInDocument') }),
    comparisonTable(
      {
        caption: t('laws.foundInDocument'),
        columns: [
          t('laws.referenceAsWritten'),
          t('laws.oldLaw'),
          t('laws.newLaw'),
          t('laws.typeOfChange'),
          t('laws.compare'),
        ],
        rows: references.map((reference) => ({
          id: reference.key,
          header: reference.raw || reference.display,
          cells: [
            { text: `${reference.act.toUpperCase()} ${reference.section}` },
            { empty: t('laws.notFound') },
            { empty: '—' },
            {
              node: el('button', {
                type: 'button',
                className: 'btn btn--small',
                text: t('laws.compare'),
                onclick: () => {
                  const search = document.getElementById('law-search');
                  if (search) {
                    search.value = `${reference.act.toUpperCase()} ${reference.section}`;
                    search.form?.requestSubmit();
                  }
                },
              }),
            },
          ],
        })),
      },
      { t },
    ),
  ]);
}

/**
 * Render the result of a lookup.
 *
 * @param {object} found The `/laws/lookup` result.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The result.
 */
function lookupResult(found, deps) {
  const { t } = deps;
  if (!found?.mappings?.length) {
    return el('div', { className: 'stack-sm' }, [
      el('p', { className: 'empty-state', text: t('laws.notFound') }),
      found?.suggestions?.length > 0 &&
        el('p', {}, [
          `${t('laws.suggestions')}: `,
          ...found.suggestions.map((suggestion) => el('span', { className: 'chip', text: suggestion })),
        ]),
    ]);
  }

  return el(
    'div',
    { className: 'stack' },
    found.mappings.map((mapping) => mappingCard(mapping, found, deps)),
  );
}

/**
 * Render one mapping, with the side-by-side comparison beneath it.
 *
 * @param {object} mapping The mapping row.
 * @param {object} found The whole lookup result.
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The card.
 */
function mappingCard(mapping, found, deps) {
  const { t } = deps;
  const newSide = mapping.new?.[0];

  const rows = [
    {
      id: 'section',
      header: t('laws.sectionAndTitle'),
      cells: [
        { text: `${mapping.old.act.toUpperCase()} ${mapping.old.section} — ${mapping.old.title}` },
        newSide
          ? { text: `${newSide.act.toUpperCase()} ${newSide.section} — ${newSide.title}` }
          : { empty: t('laws.noEquivalent') },
      ],
    },
  ];

  const texts = found.provisions || {};
  const oldText = texts[`${mapping.old.act}:${mapping.old.section}`];
  const newText = newSide ? texts[`${newSide.act}:${newSide.section}`] : null;

  rows.push({
    id: 'text',
    header: t('laws.text'),
    cells: [
      oldText ? { text: oldText.text } : { empty: t('laws.notStored') },
      newText ? { text: newText.text } : { empty: t('laws.notStored') },
    ],
  });

  if (found.diff) {
    rows.push({
      id: 'diff',
      header: t('compare.whatChanged'),
      cells: [{ node: el('div', {}, [diffFragment(found.diff, t)]) }, { empty: '—' }],
    });
  }

  if (found.punishment) {
    rows.push({
      id: 'punishment',
      header: t('laws.punishment'),
      cells: [
        found.punishment.old ? { text: found.punishment.old } : { empty: t('compare.notSpecified') },
        found.punishment.new ? { text: found.punishment.new } : { empty: t('compare.notSpecified') },
      ],
    });
  }

  rows.push({
    id: 'when',
    header: t('laws.whenApplies'),
    cells: [{ text: t('laws.whenAppliesText') }, { text: t('laws.whenAppliesText') }],
  });

  rows.push({
    id: 'sources',
    header: t('laws.sources'),
    cells: [
      { node: sourceCell(mapping.source, t) },
      { node: sourceCell(mapping.source, t) },
    ],
  });

  return el('section', { className: 'stack-sm' }, [
    el('div', { className: 'row-between' }, [
      el('h2', { className: 'flush', text: `${mapping.old.act.toUpperCase()} ${mapping.old.section}` }),
      el('div', { className: 'row' }, [
        el('span', { className: 'chip', text: t(`laws.changeTypes.${mapping.change_type}`) }),
        mapping.review_status !== 'verified' &&
          el('span', { className: 'badge badge--unreviewed' }, [icon('medium'), t('laws.unreviewed')]),
      ]),
    ]),
    mapping.review_status !== 'verified' &&
      el('p', { className: 'notice notice--warning', text: t('laws.unreviewedNote') }),
    mapping.note && el('p', { className: 'source-note', text: mapping.note }),
    comparisonTable(
      {
        caption: `${mapping.old.act.toUpperCase()} ${mapping.old.section} → ${newSide ? `${newSide.act.toUpperCase()} ${newSide.section}` : t('laws.noEquivalent')}`,
        columns: [t('laws.aspect'), t('laws.oldLaw'), t('laws.newLaw')],
        rows,
      },
      { t },
    ),
    el('div', { className: 'row no-print' }, [
      el('button', {
        type: 'button',
        className: 'btn btn--small',
        text: t('draft.downloadWord'),
        onclick: () => deps.onExport({ format: 'docx', mapping }),
      }),
      el('button', {
        type: 'button',
        className: 'btn btn--small',
        text: t('draft.downloadPdf'),
        onclick: () => deps.onExport({ format: 'pdf', mapping }),
      }),
    ]),
  ]);
}

/**
 * Render the source of a row.
 *
 * @param {object} source `{ document, page, url }`.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {HTMLElement} The cell content.
 */
function sourceCell(source, t) {
  return el('div', { className: 'stack-sm' }, [
    el('p', { className: 'source-note flush', text: source?.document || '' }),
    source?.page ? el('p', { className: 'source-note flush', text: `p. ${source.page}` }) : null,
    source?.url ? externalLink(source.url, source.url, t('a11y.newTab')) : null,
    el('p', { className: 'source-note flush', text: t('laws.sourceNote') }),
  ]);
}

/**
 * Render the "new in the new codes" and "not carried forward" lists.
 *
 * @param {object} deps Render dependencies.
 * @returns {HTMLElement} The browse section.
 */
function browseLists({ t, onBrowse, onError }) {
  const make = (kind, titleKey) => {
    const list = el('ul', {});
    const details = el('details', { className: 'card' }, [
      el('summary', { text: t(titleKey) }),
      list,
    ]);
    details.addEventListener(
      'toggle',
      () => {
        if (!details.open || list.children.length > 0) return;
        onBrowse(kind)
          .then((rows) => {
            if (rows.length === 0) {
              list.append(el('li', { className: 'empty-cell', text: t('laws.notFound') }));
              return;
            }
            for (const row of rows) {
              const side = row.new?.[0] || row.old;
              list.append(el('li', { text: `${side.act.toUpperCase()} ${side.section} — ${side.title}` }));
            }
          })
          .catch(onError);
      },
      { once: false },
    );
    return details;
  };

  return el('div', { className: 'stack-sm' }, [
    make('new', 'laws.browseNew'),
    make('removed', 'laws.browseRemoved'),
  ]);
}
