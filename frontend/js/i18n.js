/**
 * Translation lookup.
 *
 * Strings live in `frontend/i18n/*.json`. A missing key falls back to English
 * and then to the key itself, so a gap in a translation shows as untranslated
 * text rather than a blank interface.
 */

const FALLBACK = 'en';

/**
 * Read a dotted key out of a nested object.
 *
 * @param {object} source The bundle.
 * @param {string} key A dotted path such as `trust.verified`.
 * @returns {string|undefined} The string, if present.
 */
export function lookup(source, key) {
  return String(key)
    .split('.')
    .reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), source);
}

/**
 * Fill `{placeholders}` in a template.
 *
 * @param {string} template The string.
 * @param {object} values Replacements.
 * @returns {string} The filled string.
 */
export function interpolate(template, values) {
  if (!values) return template;
  return String(template).replace(/\{(\w+)\}/g, (match, name) =>
    Object.hasOwn(values, name) ? String(values[name]) : match,
  );
}

/**
 * Build a translator.
 *
 * @param {object} bundles Loaded bundles, keyed by language.
 * @param {string} language The chosen language.
 * @returns {(key: string, values?: object) => string} The translator.
 */
export function translator(bundles, language) {
  const primary = bundles[language] || {};
  const fallback = bundles[FALLBACK] || {};
  return (key, values) => {
    const template = lookup(primary, key) ?? lookup(fallback, key) ?? key;
    return interpolate(template, values);
  };
}

/**
 * Pick the language to start in.
 *
 * @param {string[]} supported Languages the app has bundles for.
 * @param {string|null} stored A previously chosen language, if any.
 * @param {string[]} preferred The browser's preferred languages.
 * @returns {string} The language to use.
 */
export function initialLanguage(supported, stored, preferred) {
  if (stored && supported.includes(stored)) return stored;
  for (const tag of preferred || []) {
    const base = String(tag).split('-')[0];
    if (supported.includes(base)) return base;
  }
  return FALLBACK;
}
