import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { termsInDocument } from '../js/views/glossary.js';

const ENTRIES = [
  { term: 'indemnify', aliases: ['indemnity'], meaning: { en: 'Cover losses.', hi: 'x', mr: 'y' } },
  { term: 'lock-in period', aliases: [], meaning: { en: 'A minimum period.', hi: 'x', mr: 'y' } },
  { term: 'arbitration', aliases: [], meaning: { en: 'A private decision.', hi: 'x', mr: 'y' } },
];

const doc = (text, defined = []) => ({
  clauses: [{ id: 'C1', text }],
  defined_terms: defined,
});

describe('choosing terms to explain', () => {
  it('offers a general meaning for a term the document uses', () => {
    const terms = termsInDocument(doc('The Licensee shall indemnify the Licensor.'), ENTRIES);
    assert.deepEqual(terms.map((entry) => entry.term), ['indemnify']);
    assert.equal(terms[0].isOwn, false);
  });

  it('matches a term by its alias', () => {
    const terms = termsInDocument(doc('An indemnity applies.'), ENTRIES);
    assert.equal(terms[0].term, 'indemnify');
  });

  it('offers nothing for a term the document never uses', () => {
    assert.deepEqual(termsInDocument(doc('Rent is payable monthly.'), ENTRIES), []);
  });

  it("prefers the document's own definition over the general meaning", () => {
    const terms = termsInDocument(
      doc('The lock-in period applies.', [
        { term: 'lock-in period', definition: 'The first eleven months.', clause_id: 'C1' },
      ]),
      ENTRIES,
    );
    assert.equal(terms.length, 1);
    assert.equal(terms[0].isOwn, true);
    assert.equal(terms[0].meaning, 'The first eleven months.');
    assert.equal(terms[0].clauseId, 'C1');
  });

  it("keeps every term the document defines, even ones it does not ship", () => {
    const terms = termsInDocument(
      doc('Nothing else here.', [{ term: 'Premises', definition: 'Flat 7B.', clause_id: 'C2' }]),
      ENTRIES,
    );
    assert.deepEqual(terms.map((entry) => entry.term), ['Premises']);
  });

  it('sorts terms alphabetically so the list is scannable', () => {
    const terms = termsInDocument(
      doc('Arbitration applies, and the Licensee shall indemnify the Licensor.'),
      ENTRIES,
    );
    assert.deepEqual(terms.map((entry) => entry.term), ['arbitration', 'indemnify']);
  });

  it('is case insensitive about the document text', () => {
    assert.equal(termsInDocument(doc('SHALL INDEMNIFY'), ENTRIES).length, 1);
  });

  it('handles a document with nothing in it', () => {
    assert.deepEqual(termsInDocument(null, ENTRIES), []);
    assert.deepEqual(termsInDocument(doc('text'), null), []);
  });
});
