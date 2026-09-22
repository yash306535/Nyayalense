import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { describe, it } from 'node:test';

import { initialLanguage, interpolate, lookup, translator } from '../js/i18n.js';

const LANGUAGES = ['en', 'hi', 'mr'];
const bundles = Object.fromEntries(
  LANGUAGES.map((name) => [name, JSON.parse(readFileSync(new URL(`../i18n/${name}.json`, import.meta.url)))]),
);

function keys(node, prefix = '') {
  return Object.entries(node).flatMap(([key, value]) => {
    const path = prefix ? `${prefix}.${key}` : key;
    return typeof value === 'object' && value !== null ? keys(value, path) : [path];
  });
}

describe('the string bundles', () => {
  it('ships one file per supported language', () => {
    const files = readdirSync(new URL('../i18n/', import.meta.url)).filter((f) => f.endsWith('.json'));
    assert.deepEqual(files.sort(), ['en.json', 'hi.json', 'mr.json']);
  });

  it('gives every language exactly the same keys', () => {
    const english = keys(bundles.en).sort();
    for (const language of ['hi', 'mr']) {
      assert.deepEqual(keys(bundles[language]).sort(), english, `${language} differs from en`);
    }
  });

  it('leaves no string empty', () => {
    for (const language of LANGUAGES) {
      for (const key of keys(bundles[language])) {
        assert.ok(lookup(bundles[language], key).trim().length > 0, `${language}.${key} is empty`);
      }
    }
  });

  it('uses the same placeholders in every language', () => {
    const placeholders = (text) => (text.match(/\{(\w+)\}/g) || []).sort();
    for (const key of keys(bundles.en)) {
      const expected = placeholders(lookup(bundles.en, key));
      for (const language of ['hi', 'mr']) {
        assert.deepEqual(placeholders(lookup(bundles[language], key)), expected, `${language}.${key}`);
      }
    }
  });
});

describe('lookup and interpolation', () => {
  it('reads a dotted key', () => {
    assert.equal(lookup({ a: { b: 'c' } }, 'a.b'), 'c');
  });

  it('returns undefined for a missing key', () => {
    assert.equal(lookup({ a: {} }, 'a.b.c'), undefined);
  });

  it('fills placeholders', () => {
    assert.equal(interpolate('{a} and {b}', { a: 1, b: 2 }), '1 and 2');
  });

  it('leaves an unknown placeholder in place rather than blanking it', () => {
    assert.equal(interpolate('{a} and {b}', { a: 1 }), '1 and {b}');
  });
});

describe('the translator', () => {
  const t = translator(bundles, 'hi');

  it('returns the chosen language', () => {
    assert.equal(t('app.name'), bundles.hi.app.name);
  });

  it('falls back to English for a key a translation lacks', () => {
    const partial = translator({ en: bundles.en, hi: { app: {} } }, 'hi');
    assert.equal(partial('app.name'), bundles.en.app.name);
  });

  it('falls back to the key itself when nothing has it', () => {
    assert.equal(t('nothing.here.at.all'), 'nothing.here.at.all');
  });
});

describe('choosing the starting language', () => {
  it('prefers what the user chose before', () => {
    assert.equal(initialLanguage(LANGUAGES, 'mr', ['en-GB']), 'mr');
  });

  it('ignores a stored language that is not supported', () => {
    assert.equal(initialLanguage(LANGUAGES, 'fr', ['hi-IN']), 'hi');
  });

  it('falls back to the browser preference', () => {
    assert.equal(initialLanguage(LANGUAGES, null, ['mr-IN', 'en-US']), 'mr');
  });

  it('falls back to English when nothing matches', () => {
    assert.equal(initialLanguage(LANGUAGES, null, ['fr-FR']), 'en');
    assert.equal(initialLanguage(LANGUAGES, null, []), 'en');
  });
});
