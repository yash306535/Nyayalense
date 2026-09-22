/**
 * DOM helpers.
 *
 * Every element in this application is built here, from `createElement` and
 * `textContent`. Nothing is ever assembled as an HTML string, so a clause that
 * contains `<script>` is displayed rather than executed, and the strict
 * Content-Security-Policy needs no exceptions.
 */

/**
 * Create an element.
 *
 * @param {string} tag Tag name.
 * @param {object} [options] Attributes, classes, dataset and text.
 * @param {(Node|string|null|undefined|false)[]} [children] Child nodes or text.
 * @returns {HTMLElement} The new element.
 */
export function el(tag, options = {}, children = []) {
  const node = document.createElement(tag);
  const { className, text, html: _ignored, dataset, attrs, ...rest } = options;

  if (className) node.className = className;
  if (text !== undefined && text !== null) node.textContent = String(text);

  for (const [key, value] of Object.entries(dataset || {})) {
    node.dataset[key] = String(value);
  }
  for (const [key, value] of Object.entries(attrs || {})) {
    if (value === false || value === null || value === undefined) continue;
    node.setAttribute(key, value === true ? '' : String(value));
  }
  for (const [key, value] of Object.entries(rest)) {
    if (typeof value === 'function') node.addEventListener(key.replace(/^on/, ''), value);
  }

  append(node, children);
  return node;
}

/**
 * Append children, skipping empty values so callers can use `&&` inline.
 *
 * @param {HTMLElement} parent Element to append to.
 * @param {(Node|string|null|undefined|false)[]|Node|string} children What to append.
 * @returns {HTMLElement} The parent.
 */
export function append(parent, children) {
  const list = Array.isArray(children) ? children : [children];
  for (const child of list) {
    if (child === null || child === undefined || child === false || child === '') continue;
    parent.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return parent;
}

/**
 * Remove every child of an element.
 *
 * @param {HTMLElement} node Element to empty.
 * @returns {HTMLElement} The same element.
 */
export function clear(node) {
  node.replaceChildren();
  return node;
}

/**
 * Replace an element's children in one operation.
 *
 * @param {HTMLElement} node Element to fill.
 * @param {(Node|string|null|undefined|false)[]|Node|string} children New content.
 * @returns {HTMLElement} The same element.
 */
export function fill(node, children) {
  clear(node);
  return append(node, children);
}

/**
 * Build text with some ranges wrapped in `<mark>`.
 *
 * Used to highlight a verified quote inside its clause. Working from offsets
 * and text nodes keeps the document's own characters intact, whatever they are.
 *
 * @param {string} text The full text.
 * @param {{start: number, end: number}[]} ranges Ranges to mark, any order.
 * @returns {DocumentFragment} The text with marked ranges.
 */
export function highlight(text, ranges) {
  const fragment = document.createDocumentFragment();
  let cursor = 0;

  for (const range of mergeRanges(ranges, text.length)) {
    if (range.start > cursor) {
      fragment.append(document.createTextNode(text.slice(cursor, range.start)));
    }
    fragment.append(el('mark', { text: text.slice(range.start, range.end) }));
    cursor = range.end;
  }
  if (cursor < text.length) fragment.append(document.createTextNode(text.slice(cursor)));
  return fragment;
}

/**
 * Sort ranges, drop empty ones and merge those that overlap.
 *
 * @param {{start: number, end: number}[]} ranges Ranges to tidy.
 * @param {number} limit Length of the text the ranges point into.
 * @returns {{start: number, end: number}[]} Disjoint ranges in order.
 */
export function mergeRanges(ranges, limit) {
  const clean = (ranges || [])
    .map((range) => ({
      start: Math.max(0, Math.min(range.start ?? 0, limit)),
      end: Math.max(0, Math.min(range.end ?? 0, limit)),
    }))
    .filter((range) => range.end > range.start)
    .sort((a, b) => a.start - b.start);

  const merged = [];
  for (const range of clean) {
    const last = merged[merged.length - 1];
    if (last && range.start <= last.end) {
      last.end = Math.max(last.end, range.end);
    } else {
      merged.push({ ...range });
    }
  }
  return merged;
}

/**
 * Create a visually hidden label for screen readers.
 *
 * @param {string} text What to announce.
 * @returns {HTMLElement} A hidden span.
 */
export function srOnly(text) {
  return el('span', { className: 'sr-only', text });
}

/**
 * Create an external link, marked as opening in a new tab.
 *
 * @param {string} href Destination.
 * @param {string} label Visible text.
 * @param {string} newTabLabel Hidden text such as "(opens in a new tab)".
 * @returns {HTMLElement} The anchor.
 */
export function externalLink(href, label, newTabLabel) {
  return el(
    'a',
    { className: 'external', attrs: { href, target: '_blank', rel: 'noopener noreferrer' } },
    [label, ' ', srOnly(newTabLabel), icon('external')],
  );
}

/** Inline icons, drawn as SVG so they scale with text and follow `currentColor`. */
const ICON_PATHS = {
  external: 'M5 11L11 5M11 5H6.5M11 5v4.5M9 10.5v2a1 1 0 0 1-1 1H3.5a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1h2',
  high: 'M8 2.5 14.5 13.5h-13z M8 6.5v3.2 M8 11.6v.9',
  medium: 'M8 1.8a6.2 6.2 0 1 0 0 12.4A6.2 6.2 0 0 0 8 1.8z M8 5v3.6 M8 10.4v.9',
  low: 'M8 1.8a6.2 6.2 0 1 0 0 12.4A6.2 6.2 0 0 0 8 1.8z M5.4 8.2l1.8 1.8 3.4-3.6',
  check: 'M3 8.5 6.5 12 13 4.5',
  cross: 'M4 4l8 8M12 4l-8 8',
  question: 'M8 1.8a6.2 6.2 0 1 0 0 12.4A6.2 6.2 0 0 0 8 1.8z M6.2 6.1a1.9 1.9 0 0 1 3.6.7c0 1.3-1.8 1.5-1.8 2.7 M8 11.7v.8',
  seal: 'M8 1.6l1.7 1.2 2-.3.6 2 1.7 1.2-1 1.8.4 2-2 .6-1.2 1.7L8 11.2l-2.2.6-1.2-1.7-2-.6.4-2-1-1.8 1.7-1.2.6-2 2 .3z',
};

/**
 * Create an inline icon.
 *
 * Icons are decorative: the text beside them carries the meaning, so nothing
 * is ever signalled by a shape or a colour alone.
 *
 * @param {keyof typeof ICON_PATHS} name Which icon.
 * @returns {SVGElement} The icon.
 */
export function icon(name) {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 16 16');
  svg.setAttribute('aria-hidden', 'true');
  svg.setAttribute('focusable', 'false');
  svg.classList.add('icon', `icon-${name}`);
  const path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
  path.setAttribute('d', ICON_PATHS[name] || ICON_PATHS.check);
  path.setAttribute('fill', 'none');
  path.setAttribute('stroke', 'currentColor');
  path.setAttribute('stroke-width', '1.4');
  path.setAttribute('stroke-linecap', 'round');
  path.setAttribute('stroke-linejoin', 'round');
  svg.append(path);
  return svg;
}
