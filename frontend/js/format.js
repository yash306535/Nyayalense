/**
 * Formatting that must be correct in every supported locale.
 *
 * Amounts and dates are read as facts, so they are formatted with `Intl` in the
 * Indian locales rather than by hand. This module is pure, so `node --test`
 * covers it.
 */

const LOCALES = { en: 'en-IN', hi: 'hi-IN', mr: 'mr-IN' };

/**
 * Resolve a UI language to its Indian locale.
 *
 * @param {string} language One of `en`, `hi`, `mr`.
 * @returns {string} A BCP 47 locale tag.
 */
export function localeFor(language) {
  return LOCALES[language] || LOCALES.en;
}

/**
 * Format a number in the Indian digit grouping.
 *
 * @param {number|string} value The number.
 * @param {string} language UI language.
 * @returns {string} The formatted number, or the input unchanged if not numeric.
 */
export function formatNumber(value, language) {
  const number = typeof value === 'number' ? value : Number(String(value).replace(/,/g, ''));
  if (!Number.isFinite(number)) return String(value);
  return new Intl.NumberFormat(localeFor(language)).format(number);
}

/**
 * Format an amount in rupees.
 *
 * @param {number|string} value The amount.
 * @param {string} language UI language.
 * @returns {string} The formatted amount.
 */
export function formatMoney(value, language) {
  // Stripping non-digits from text with no digits in it yields an empty string,
  // which Number() reads as zero. A term worth "to be agreed" must never be
  // shown as a rupee amount, so text without a digit is returned as written.
  if (typeof value !== 'number' && !/\d/.test(String(value ?? ''))) return String(value ?? '');
  const number = typeof value === 'number' ? value : Number(String(value).replace(/[^\d.-]/g, ''));
  if (!Number.isFinite(number)) return String(value);
  return new Intl.NumberFormat(localeFor(language), {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: number % 1 === 0 ? 0 : 2,
  }).format(number);
}

/**
 * Format an ISO date as a readable date.
 *
 * @param {string} iso A `yyyy-mm-dd` date.
 * @param {string} language UI language.
 * @returns {string} The formatted date, or the input if it is not a date.
 */
export function formatDate(iso, language) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(iso || '')) return iso || '';
  const date = new Date(`${iso}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(localeFor(language), {
    day: 'numeric',
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(date);
}

/**
 * Build the trust line shown on every result.
 *
 * It states plainly how much of the result survived verification, including
 * when nothing did, because a silent result is what a general assistant gives.
 *
 * @param {{total: number, verified: number, removed: object[]}} report The report.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {{text: string, tone: 'all'|'partial'|'none'}} Line and its tone.
 */
export function trustLine(report, t) {
  const total = report?.total ?? 0;
  const verified = report?.verified ?? 0;
  if (total === 0) return { text: t('trust.nothingToCheck'), tone: 'none' };
  if (verified === 0) return { text: t('trust.noneVerified'), tone: 'none' };
  return {
    text: t('trust.verified', { verified, total }),
    tone: verified === total ? 'all' : 'partial',
  };
}

/**
 * Build the sentence disclosing removed statements.
 *
 * @param {{removed: object[]}} report The report.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {string} The sentence, or an empty string when nothing was removed.
 */
export function removalNote(report, t) {
  const removed = (report?.removed || []).length;
  if (!removed) return '';
  return removed === 1 ? t('trust.removedOne') : t('trust.removedMany', { removed });
}

/**
 * Turn a clause into the reference shown beside a quote.
 *
 * @param {{label?: string, id: string, page?: number}} clause The clause.
 * @param {(key: string, values?: object) => string} t Translation function.
 * @returns {string} Something like "Clause 7.2, page 3".
 */
export function clauseReference(clause, t) {
  if (!clause) return '';
  const name = clause.label ? t('clause.numbered', { label: clause.label }) : clause.id;
  return clause.page ? t('clause.withPage', { name, page: clause.page }) : name;
}

/**
 * Build a download file name.
 *
 * @param {string} base A slug such as `deposit-refund-request`.
 * @param {string} extension File extension without the dot.
 * @param {Date} [today] The date to stamp. Defaults to now.
 * @returns {string} A safe file name.
 */
export function downloadName(base, extension, today = new Date()) {
  const slug = String(base)
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 60) || 'nyayalens';
  return `${slug}-${today.toISOString().slice(0, 10)}.${extension}`;
}

/**
 * Truncate text at a word boundary.
 *
 * @param {string} text The text.
 * @param {number} limit Maximum characters.
 * @returns {string} The text, shortened with an ellipsis if it was too long.
 */
export function truncate(text, limit) {
  const value = String(text ?? '');
  if (value.length <= limit) return value;
  const cut = value.slice(0, limit);
  const space = cut.lastIndexOf(' ');
  return `${(space > limit * 0.6 ? cut.slice(0, space) : cut).trimEnd()}…`;
}
