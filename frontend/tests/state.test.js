import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  analysisBody,
  answerReceived,
  createStore,
  documentLoaded,
  findClause,
  highlightRanges,
  initialState,
  recentTurns,
  situations,
} from '../js/state.js';

const RESULT = {
  document: { id: 'abc', doc_type: 'rental_leave_licence', clauses: [{ id: 'C1', text: 'Rent.' }] },
  law_references: [{ act: 'ipc', section: '420' }],
  suggested_roles: ['tenant', 'landlord'],
};

describe('the store', () => {
  it('notifies subscribers with the keys that changed', () => {
    const store = createStore();
    const seen = [];
    store.subscribe((_, changed) => seen.push(changed));
    store.set({ language: 'hi' });
    assert.deepEqual(seen, [['language']]);
  });

  it('does not notify when nothing actually changed', () => {
    const store = createStore();
    let calls = 0;
    store.subscribe(() => (calls += 1));
    store.set({ language: 'en' });
    assert.equal(calls, 0);
  });

  it('stops notifying after unsubscribing', () => {
    const store = createStore();
    let calls = 0;
    const off = store.subscribe(() => (calls += 1));
    off();
    store.set({ language: 'mr' });
    assert.equal(calls, 0);
  });

  it('updates from a function of the current state', () => {
    const store = createStore();
    store.update((state) => ({ answers: [...state.answers, { question: 'q' }] }));
    assert.equal(store.get().answers.length, 1);
  });
});

describe('loading a document', () => {
  it('clears everything from the previous document', () => {
    const before = { ...initialState(), overview: { x: 1 }, answers: [{}], compare: { y: 2 } };
    const patch = documentLoaded(before, RESULT);
    assert.equal(patch.overview, null);
    assert.equal(patch.review, null);
    assert.equal(patch.compare, null);
    assert.deepEqual(patch.answers, []);
  });

  it('takes the first suggested role when none was chosen', () => {
    assert.equal(documentLoaded(initialState(), RESULT).role, 'tenant');
  });

  it('keeps a role the user chose, when it still applies', () => {
    const state = { ...initialState(), role: 'landlord' };
    assert.equal(documentLoaded(state, RESULT).role, 'landlord');
  });

  it('replaces a chosen role that does not apply to the new document', () => {
    const state = { ...initialState(), role: 'borrower' };
    assert.equal(documentLoaded(state, RESULT).role, 'tenant');
  });

  it('falls back to "other" when nothing is suggested', () => {
    const patch = documentLoaded(initialState(), { ...RESULT, suggested_roles: [] });
    assert.equal(patch.role, 'other');
  });
});

describe('conversation history', () => {
  const answers = [1, 2, 3, 4, 5, 6].map((n) => ({
    question: `q${n}`,
    statements: [{ text: `a${n}` }],
  }));

  it('sends only the last four turns', () => {
    const turns = recentTurns(answers);
    assert.equal(turns.length, 4);
    assert.equal(turns[0].question, 'q3');
    assert.equal(turns[3].question, 'q6');
  });

  it('flattens statements into one answer string', () => {
    const turns = recentTurns([{ question: 'q', statements: [{ text: 'one' }, { text: 'two' }] }]);
    assert.equal(turns[0].answer, 'one two');
  });

  it('handles an answer with no statements', () => {
    assert.equal(recentTurns([{ question: 'q', statements: [] }])[0].answer, '');
  });

  it('appends a new answer without mutating the old list', () => {
    const state = { ...initialState(), answers: [{ question: 'one' }] };
    const patch = answerReceived(state, { question: 'two' });
    assert.equal(patch.answers.length, 2);
    assert.equal(state.answers.length, 1);
  });
});

describe('the request body', () => {
  it('carries the document and the reader choices', () => {
    const state = { ...initialState(), document: RESULT.document, role: 'tenant', language: 'hi' };
    const body = analysisBody(state);
    assert.equal(body.document.id, 'abc');
    assert.deepEqual(body.audience, { role: 'tenant', language: 'hi', reading_level: 'simple' });
  });
});

describe('clauses and highlights', () => {
  const state = { ...initialState(), document: RESULT.document };

  it('finds a clause by id', () => {
    assert.equal(findClause(state, 'C1').text, 'Rent.');
  });

  it('returns null for an unknown clause', () => {
    assert.equal(findClause(state, 'C99'), null);
  });

  it('collects only verified spans, and only for the clause asked for', () => {
    const statements = [
      { citations: [{ clause_id: 'C1', verified: true, span_start: 0, span_end: 4 }] },
      { citations: [{ clause_id: 'C1', verified: false, span_start: 5, span_end: 9 }] },
      { citations: [{ clause_id: 'C2', verified: true, span_start: 0, span_end: 3 }] },
    ];
    assert.deepEqual(highlightRanges(statements, 'C1'), [{ start: 0, end: 4 }]);
  });

  it('handles no statements at all', () => {
    assert.deepEqual(highlightRanges(undefined, 'C1'), []);
  });
});

describe('situations for the help strip', () => {
  it('flags a law reference when the document cites one', () => {
    const state = { ...initialState(), lawReferences: [{ act: 'ipc' }] };
    assert.ok(situations(state).includes('law_reference'));
  });

  it('flags online fraud from what the user asked', () => {
    const state = { ...initialState(), answers: [{ question: 'I was scammed on UPI' }] };
    assert.ok(situations(state).includes('online_fraud'));
  });

  it('flags a consumer complaint from a refund question', () => {
    const state = { ...initialState(), answers: [{ question: 'Can I get a refund?' }] };
    assert.ok(situations(state).includes('consumer_complaint'));
  });

  it('returns nothing when there is no signal', () => {
    assert.deepEqual(situations(initialState()), []);
  });
});
