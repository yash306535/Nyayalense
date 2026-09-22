import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  clauseReference,
  downloadName,
  formatDate,
  formatMoney,
  formatNumber,
  localeFor,
  removalNote,
  truncate,
  trustLine,
} from '../js/format.js';

const t = (key, values) =>
  values ? `${key}:${Object.entries(values).map(([k, v]) => `${k}=${v}`).join(',')}` : key;

describe('locales', () => {
  it('maps each supported language to its Indian locale', () => {
    assert.equal(localeFor('en'), 'en-IN');
    assert.equal(localeFor('hi'), 'hi-IN');
    assert.equal(localeFor('mr'), 'mr-IN');
  });

  it('falls back to English for an unknown language', () => {
    assert.equal(localeFor('xx'), 'en-IN');
  });
});

describe('numbers and money', () => {
  it('groups numbers the Indian way', () => {
    assert.equal(formatNumber(150000, 'en'), '1,50,000');
    assert.equal(formatNumber('1,50,000', 'en'), '1,50,000');
  });

  it('formats money in rupees without stray decimals', () => {
    assert.match(formatMoney(60000, 'en'), /60,000/);
    assert.ok(!formatMoney(60000, 'en').includes('.00'));
  });

  it('keeps decimals when the amount has them', () => {
    assert.match(formatMoney(60000.5, 'en'), /\.5/);
  });

  it('returns unparseable input unchanged rather than guessing', () => {
    assert.equal(formatNumber('not a number', 'en'), 'not a number');
    assert.equal(formatMoney('to be agreed', 'en'), 'to be agreed');
  });
});

describe('dates', () => {
  it('formats an ISO date readably', () => {
    assert.match(formatDate('2026-04-01', 'en'), /April/);
  });

  it('leaves anything that is not a date alone', () => {
    assert.equal(formatDate('within 30 days', 'en'), 'within 30 days');
    assert.equal(formatDate('', 'en'), '');
    assert.equal(formatDate('2026-13-45', 'en'), '2026-13-45');
  });
});

describe('the trust line', () => {
  it('reports a fully verified result', () => {
    const line = trustLine({ total: 3, verified: 3, removed: [] }, t);
    assert.equal(line.tone, 'all');
    assert.equal(line.text, 'trust.verified:verified=3,total=3');
  });

  it('reports a partly verified result', () => {
    assert.equal(trustLine({ total: 3, verified: 2, removed: [{}] }, t).tone, 'partial');
  });

  it('says plainly when nothing verified', () => {
    assert.equal(trustLine({ total: 2, verified: 0, removed: [{}, {}] }, t).text, 'trust.noneVerified');
  });

  it('says plainly when there was nothing to check', () => {
    assert.equal(trustLine({ total: 0, verified: 0, removed: [] }, t).text, 'trust.nothingToCheck');
    assert.equal(trustLine(undefined, t).text, 'trust.nothingToCheck');
  });
});

describe('disclosing removals', () => {
  it('says nothing when nothing was removed', () => {
    assert.equal(removalNote({ removed: [] }, t), '');
    assert.equal(removalNote(undefined, t), '');
  });

  it('uses the singular for one removal', () => {
    assert.equal(removalNote({ removed: [{}] }, t), 'trust.removedOne');
  });

  it('uses the plural and the count for several', () => {
    assert.equal(removalNote({ removed: [{}, {}, {}] }, t), 'trust.removedMany:removed=3');
  });
});

describe('clause references', () => {
  it('uses the document own numbering and page', () => {
    assert.equal(
      clauseReference({ label: '7.2', page: 3, id: 'C12' }, t),
      'clause.withPage:name=clause.numbered:label=7.2,page=3',
    );
  });

  it('falls back to the clause id when the document numbers nothing', () => {
    assert.match(clauseReference({ label: '', page: 1, id: 'C12' }, t), /C12/);
  });

  it('handles a missing clause', () => {
    assert.equal(clauseReference(null, t), '');
  });
});

describe('download names', () => {
  const day = new Date('2026-09-22T10:00:00Z');

  it('slugs the base and stamps the date', () => {
    assert.equal(downloadName('Deposit Refund Request', 'docx', day), 'deposit-refund-request-2026-09-22.docx');
  });

  it('strips characters that could escape a directory', () => {
    assert.equal(downloadName('../../etc/passwd', 'pdf', day), 'etc-passwd-2026-09-22.pdf');
  });

  it('never produces an empty name', () => {
    assert.equal(downloadName('!!!', 'pdf', day), 'nyayalens-2026-09-22.pdf');
  });
});

describe('truncation', () => {
  it('leaves short text alone', () => {
    assert.equal(truncate('short', 20), 'short');
  });

  it('cuts at a word boundary', () => {
    assert.equal(truncate('the quick brown fox jumps', 16), 'the quick brown…');
  });

  it('handles missing text', () => {
    assert.equal(truncate(undefined, 10), '');
  });
});
