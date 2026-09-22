/**
 * Accessibility utilities.
 *
 * Progress, results and downloads are announced in one polite live region;
 * errors go to an assertive one. Dialogs trap focus and give it back. Activating
 * a citation moves focus to the clause it points at, which is the difference
 * between a citation you can read and one you can actually check.
 */

/**
 * Announce a message in a live region.
 *
 * @param {HTMLElement} region The live region.
 * @param {string} message What to say.
 */
export function announce(region, message) {
  if (!region) return;
  // Clearing first makes a repeated message announce again.
  region.textContent = '';
  if (message) requestAnimationFrame(() => (region.textContent = message));
}

/**
 * Mark a region as busy while work is in progress.
 *
 * @param {HTMLElement} node The region.
 * @param {boolean} busy Whether work is in progress.
 */
export function setBusy(node, busy) {
  if (!node) return;
  if (busy) node.setAttribute('aria-busy', 'true');
  else node.removeAttribute('aria-busy');
}

/**
 * Move focus to an element that is not normally focusable.
 *
 * @param {HTMLElement|null} node The element to focus.
 */
export function focusTarget(node) {
  if (!node) return;
  if (!node.hasAttribute('tabindex')) node.setAttribute('tabindex', '-1');
  node.focus({ preventScroll: true });
  node.scrollIntoView({ block: 'center', behavior: prefersReducedMotion() ? 'auto' : 'smooth' });
}

/** @returns {boolean} Whether the viewer asked for reduced motion. */
export function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia
    ? window.matchMedia('(prefers-reduced-motion: reduce)').matches
    : false;
}

const FOCUSABLE = [
  'a[href]',
  'button:not([disabled])',
  'input:not([disabled]):not([type="hidden"])',
  'select:not([disabled])',
  'textarea:not([disabled])',
  '[tabindex]:not([tabindex="-1"])',
].join(',');

/**
 * List the focusable elements inside a container, in tab order.
 *
 * @param {HTMLElement} container The container.
 * @returns {HTMLElement[]} Focusable elements.
 */
export function focusable(container) {
  return [...container.querySelectorAll(FOCUSABLE)].filter(
    (node) => node.offsetParent !== null || node === document.activeElement,
  );
}

/**
 * Open a dialog, trapping focus until it closes and then restoring it.
 *
 * @param {HTMLDialogElement} dialog The dialog.
 * @returns {() => void} A function that closes it.
 */
export function openDialog(dialog) {
  const previous = document.activeElement;

  const onKeydown = (event) => {
    if (event.key !== 'Tab') return;
    const items = focusable(dialog);
    if (items.length === 0) return;
    const first = items[0];
    const last = items[items.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  };

  const close = () => {
    dialog.removeEventListener('keydown', onKeydown);
    if (dialog.open) dialog.close();
    if (previous instanceof HTMLElement) previous.focus();
  };

  dialog.addEventListener('keydown', onKeydown);
  dialog.addEventListener('close', close, { once: true });
  dialog.showModal();
  focusable(dialog)[0]?.focus();
  return close;
}

/**
 * Implement the WAI-ARIA tabs pattern on a tablist.
 *
 * Roving tabindex, arrow keys, Home and End, exactly as the pattern requires,
 * because a half-implemented pattern is worse than none.
 *
 * @param {HTMLElement} tablist The element with `role="tablist"`.
 * @param {(id: string) => void} onSelect Called with the selected tab's id.
 */
export function wireTabs(tablist, onSelect) {
  const tabs = () => [...tablist.querySelectorAll('[role="tab"]')];

  const select = (tab) => {
    for (const other of tabs()) {
      const chosen = other === tab;
      other.setAttribute('aria-selected', String(chosen));
      other.tabIndex = chosen ? 0 : -1;
    }
    tab.focus();
    onSelect(tab.dataset.tab);
  };

  tablist.addEventListener('click', (event) => {
    const tab = event.target.closest('[role="tab"]');
    if (tab) select(tab);
  });

  tablist.addEventListener('keydown', (event) => {
    const items = tabs();
    const index = items.indexOf(document.activeElement);
    if (index < 0) return;
    const moves = {
      ArrowRight: index + 1,
      ArrowLeft: index - 1,
      Home: 0,
      End: items.length - 1,
    };
    if (!(event.key in moves)) return;
    event.preventDefault();
    const next = (moves[event.key] + items.length) % items.length;
    select(items[next]);
  });
}
