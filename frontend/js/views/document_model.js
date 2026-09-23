/**
 * Rendering a document model in the browser.
 *
 * The same model produces the Word file and the PDF, so what appears here is
 * what downloads. Values that came from the reader's own confirmed facts are
 * marked, so they can see which parts of a letter are theirs.
 */

import { el } from '../dom.js';

const MAX_HEADING_LEVEL = 4;

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
    if (block.type === 'heading') return el(`h${Math.min(block.level || 2, MAX_HEADING_LEVEL)}`, { text: inlineText(block) });
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
        className: 'from-fact',
        text: run.text,
      });
    }
    if (run.bold) return el('strong', { text: run.text });
    if (run.italic) return el('em', { text: run.text });
    return document.createTextNode(run.text);
  });
}
