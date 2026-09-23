/**
 * Client-held application state.
 *
 * The API is stateless: the browser holds the clause map and sends it back with
 * every request. This module is that store. It is pure, observable and has no
 * DOM dependency, so `node --test` covers the reducers.
 */

/** @returns {object} The state an empty session starts from. */
export function initialState() {
  return {
    meta: null,
    language: 'en',
    readingLevel: 'simple',
    role: 'other',
    view: 'upload',
    tab: 'overview',
    document: null,
    lawReferences: [],
    suggestedRoles: [],
    overview: null,
    review: null,
    compare: null,
    scenario: null,
    answers: [],
    activeCitation: null,
    status: { busy: false, message: '' },
    error: null,
    assistantMode: 'compare',
    legalAnswers: [],
  };
}

/**
 * Create an observable store.
 *
 * @param {object} [state] Starting state.
 * @returns {{get: Function, set: Function, update: Function, subscribe: Function}} The store.
 */
export function createStore(state = initialState()) {
  let current = state;
  const listeners = new Set();

  const notify = (changed) => {
    for (const listener of listeners) listener(current, changed);
  };

  return {
    /** @returns {object} The current state. */
    get: () => current,

    /**
     * Merge a patch into the state and notify subscribers.
     *
     * @param {object} patch Fields to change.
     */
    set(patch) {
      const changed = Object.keys(patch).filter((key) => current[key] !== patch[key]);
      if (changed.length === 0) return;
      current = { ...current, ...patch };
      notify(changed);
    },

    /**
     * Replace the state using a function of the current state.
     *
     * @param {(state: object) => object} fn Reducer.
     */
    update(fn) {
      this.set(fn(current));
    },

    /**
     * Subscribe to changes.
     *
     * @param {(state: object, changed: string[]) => void} listener Callback.
     * @returns {() => void} Unsubscribe.
     */
    subscribe(listener) {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
  };
}

/**
 * Record a newly ingested document, clearing anything from the previous one.
 *
 * @param {object} state Current state.
 * @param {object} result The `/documents` response.
 * @returns {object} The patch to apply.
 */
export function documentLoaded(state, result) {
  const suggested = result.suggested_roles || [];
  return {
    document: result.document,
    lawReferences: result.law_references || [],
    suggestedRoles: suggested,
    // Keep a role the user chose deliberately; otherwise take the first suggestion.
    role: state.role !== 'other' && suggested.includes(state.role) ? state.role : suggested[0] || 'other',
    view: 'document',
    tab: 'overview',
    overview: null,
    review: null,
    compare: null,
    scenario: null,
    answers: [],
    activeCitation: null,
    error: null,
  };
}

/**
 * Append a question and its answer to the conversation.
 *
 * @param {object} state Current state.
 * @param {object} answer The `/qa` response.
 * @returns {object} The patch to apply.
 */
export function answerReceived(state, answer) {
  return { answers: [...state.answers, answer] };
}

/**
 * Append a general legal question and its answer to that conversation.
 *
 * Kept separate from `answers`, which is one document's Q&A history: a legal
 * question draws on the packaged statute text, not on whatever document is
 * open, so it outlives switching documents or having none open at all.
 *
 * @param {object} state Current state.
 * @param {object} entry The `/laws/qa` response.
 * @returns {object} The patch to apply.
 */
export function legalAnswerReceived(state, entry) {
  return { legalAnswers: [...state.legalAnswers, entry] };
}

/**
 * Build the last few turns to send as context for a follow-up question.
 *
 * @param {object[]} answers Every answer so far.
 * @param {number} [limit] How many turns to include.
 * @returns {{question: string, answer: string}[]} The turns, oldest first.
 */
export function recentTurns(answers, limit = 4) {
  return answers.slice(-limit).map((entry) => ({
    question: entry.question,
    answer: (entry.statements || []).map((statement) => statement.text).join(' ').slice(0, 4000),
  }));
}

/**
 * Build the request body every analysis endpoint takes.
 *
 * @param {object} state Current state.
 * @returns {object} The body.
 */
export function analysisBody(state) {
  return {
    document: state.document,
    audience: {
      role: state.role,
      language: state.language,
      reading_level: state.readingLevel,
    },
  };
}

/**
 * Find a clause by id.
 *
 * @param {object} state Current state.
 * @param {string} clauseId The clause id.
 * @returns {object|null} The clause, or null.
 */
export function findClause(state, clauseId) {
  return (state.document?.clauses || []).find((clause) => clause.id === clauseId) || null;
}

/**
 * Collect the highlight ranges for one clause from a list of statements.
 *
 * @param {object[]} statements Verified statements.
 * @param {string} clauseId The clause to collect for.
 * @returns {{start: number, end: number}[]} Ranges into that clause's text.
 */
export function highlightRanges(statements, clauseId) {
  return (statements || [])
    .flatMap((statement) => statement.citations || [])
    .filter((citation) => citation.clause_id === clauseId && citation.verified)
    .map((citation) => ({ start: citation.span_start, end: citation.span_end }));
}

/**
 * Work out which situations apply, so the help strip can be relevant.
 *
 * @param {object} state Current state.
 * @returns {string[]} Situation keys for `GET /resources`.
 */
export function situations(state) {
  const keys = new Set();
  if ((state.lawReferences || []).length > 0) keys.add('law_reference');
  const text = [
    state.document?.title || '',
    ...(state.answers || []).map((answer) => answer.question),
  ]
    .join(' ')
    .toLowerCase();
  if (/fraud|cheat|online|upi|phish|scam/.test(text)) keys.add('online_fraud');
  if (/refund|claim|service|policy|loan/.test(text)) keys.add('consumer_complaint');
  return [...keys];
}
