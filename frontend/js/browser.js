/**
 * Small browser conveniences.
 *
 * Local storage can be absent or throw in a private window, and a sandboxed
 * page can refuse a download, so each of these degrades rather than failing.
 */

import { el } from './dom.js';

const REVOKE_AFTER_MS = 1000;

/**
 * Read a value from local storage, tolerating private browsing.
 *
 * @param {string} key The key.
 * @returns {string|null} The value, or null.
 */
export function readSetting(key) {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

/**
 * Write a value to local storage, tolerating private browsing.
 *
 * @param {string} key The key.
 * @param {string} value The value.
 */
export function writeSetting(key, value) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Storage is a convenience here; everything works the same without it.
  }
}

/**
 * Apply a theme, or follow the system when none is chosen.
 *
 * @param {string|null} theme `dark`, `light`, or null to follow the system.
 * @returns {boolean} Whether the dark theme is now active by explicit choice.
 */
export function applyTheme(theme) {
  if (theme === 'dark' || theme === 'light') {
    document.documentElement.dataset.theme = theme;
  } else {
    delete document.documentElement.dataset.theme;
  }
  return document.documentElement.dataset.theme === 'dark';
}

/**
 * Save a blob to the viewer's device.
 *
 * @param {Blob} blob The file.
 * @param {string} filename What to call it.
 */
export function saveBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = el('a', { className: 'sr-only', attrs: { href: url, download: filename } });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), REVOKE_AFTER_MS);
}
