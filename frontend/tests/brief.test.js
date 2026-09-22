import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { buildBrief, isUseful, topRisks, totals, verifiedStatements } from '../js/brief.js';

const verified = (text) => ({
  text,
  kind: 'direct',
  citations: [{ clause_id: 'C1', quote: 'a quote', verified: true }],
});

const unverified = (text) => ({
  text,
  kind: 'direct',
  citations: [{ clause_id: 'C1', quote: 'a quote', verified: false }],
});

describe('filtering to verified statements', () => {
  it('keeps statements that have a verified citation', () => {
    assert.equal(verifiedStatements([verified('kept')]).length, 1);
  });

  it('drops statements whose citations did not verify', () => {
    assert.deepEqual(verifiedStatements([unverified('dropped')]), []);
  });

  it('drops the unverified citations from a statement that survives', () => {
    const mixed = {
      text: 'mixed',
      citations: [
        { clause_id: 'C1', quote: 'good', verified: true },
        { clause_id: 'C2', quote: 'bad', verified: false },
      ],
    };
    assert.equal(verifiedStatements([mixed])[0].citations.length, 1);
  });

  it('handles nothing at all', () => {
    assert.deepEqual(verifiedStatements(undefined), []);
  });
});

describe('ordering risks', () => {
  it('puts the most serious first', () => {
    const risks = [
      { title: 'low one', severity: 'low' },
      { title: 'high one', severity: 'high' },
      { title: 'medium one', severity: 'medium' },
    ];
    assert.deepEqual(topRisks(risks).map((r) => r.title), ['high one', 'medium one', 'low one']);
  });

  it('caps how many are included', () => {
    const many = Array.from({ length: 20 }, (_, i) => ({ title: `r${i}`, severity: 'low' }));
    assert.equal(topRisks(many).length, 8);
  });
});

describe('summing verification', () => {
  it('adds up totals and concatenates removals', () => {
    const summed = totals([
      { total: 3, verified: 3, removed: [] },
      { total: 2, verified: 1, removed: [{ reason: 'quote_not_found' }] },
      null,
    ]);
    assert.deepEqual(summed, { total: 5, verified: 4, removed: [{ reason: 'quote_not_found' }] });
  });
});

describe('building the brief', () => {
  const input = {
    document: { doc_type: 'rental_leave_licence', title: 'Rental agreement' },
    overview: {
      summary: [verified('This is a rental agreement.'), unverified('Invented.')],
      parties: [{ name: 'Mr. A', described_as: 'Licensor', is_user: false }],
      key_terms: [
        { label: 'Deposit', value: '60,000', statements: [verified('The deposit is 60000.')] },
        { label: 'Refund timeline', value: null, statements: [] },
      ],
      obligations: [{ who: 'you', what: 'Pay rent', statements: [verified('Rent is due.')] }],
      key_dates: [{ title: 'Start', date: '2026-05-01', timing_kind: 'absolute' }],
      verification: { total: 4, verified: 3, removed: [{ reason: 'quote_not_found' }] },
    },
    review: {
      risks: [{ title: 'Forfeiture', severity: 'high', explanation: 'x', statements: [verified('q')] }],
      missing: [{ title: 'Refund deadline', why_it_matters: 'y', question_to_ask: 'z' }],
      inconsistencies: [{ title: 'Two notice periods', explanation: 'x', statements: [verified('q')] }],
      verification: { total: 3, verified: 3, removed: [] },
    },
    answers: [
      { question: 'Deposit?', answer_type: 'direct', statements: [verified('60000.')], verification: { total: 1, verified: 1, removed: [] } },
      { question: 'Weather?', answer_type: 'out_of_scope', statements: [], verification: { total: 0, verified: 0, removed: [] } },
    ],
    lawReferences: [{ act: 'ipc', section: '420', raw: 'Section 420 IPC' }],
    checklist: { facts_to_have_ready: ['Move-in date'], documents_to_bring: ['The agreement'] },
    role: 'tenant',
  };

  const brief = buildBrief(input);

  it('includes only statements that verified', () => {
    assert.equal(brief.summary.length, 1);
    assert.equal(brief.summary[0].text, 'This is a rental agreement.');
  });

  it('keeps an unspecified term as an explicit absence', () => {
    const term = brief.keyTerms.find((entry) => entry.label === 'Refund timeline');
    assert.equal(term.specified, false);
  });

  it('leaves out questions that were not about the document', () => {
    assert.deepEqual(brief.questions.map((q) => q.question), ['Deposit?']);
  });

  it('carries the law references found in the document', () => {
    assert.equal(brief.lawReferences[0].section, '420');
  });

  it('carries the static lists from the checklist', () => {
    assert.deepEqual(brief.factsToHaveReady, ['Move-in date']);
    assert.deepEqual(brief.documentsToBring, ['The agreement']);
  });

  it('sums verification across every part', () => {
    assert.equal(brief.verification.total, 8);
    assert.equal(brief.verification.verified, 7);
  });

  it('is useful once it has content', () => {
    assert.equal(isUseful(brief), true);
  });

  it('is not useful when nothing verified', () => {
    const empty = buildBrief({
      document: { doc_type: 'general_contract' },
      overview: null, review: null, answers: [], lawReferences: [], checklist: null, role: 'other',
    });
    assert.equal(isUseful(empty), false);
  });
});
