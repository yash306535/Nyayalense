/**
 * Assembling the brief for a lawyer or legal-aid clinic.
 *
 * This is a pure function of results that have already been verified. No model
 * is involved: the brief can only contain what survived verification, which is
 * what makes it safe to hand to a professional.
 */

/**
 * Build the brief.
 *
 * @param {object} input Everything gathered so far.
 * @param {object} input.document The ingested document.
 * @param {object|null} input.overview The overview result.
 * @param {object|null} input.review The review result.
 * @param {object[]} input.answers Questions asked and their answers.
 * @param {object[]} input.lawReferences Old-law references found in the text.
 * @param {object|null} input.checklist The curated checklist for this type.
 * @param {string} input.role The reader's role.
 * @returns {object} A structured brief, ready to render or export.
 */
export function buildBrief({ document: doc, overview, review, answers, lawReferences, checklist, role }) {
  return {
    role,
    docType: doc?.doc_type || '',
    title: doc?.title || '',
    summary: verifiedStatements(overview?.summary),
    parties: (overview?.parties || []).map((party) => ({
      name: party.name,
      describedAs: party.described_as,
      isUser: party.is_user,
    })),
    keyTerms: (overview?.key_terms || []).map((term) => ({
      label: term.label,
      value: term.value,
      specified: Boolean(term.value),
      statements: verifiedStatements(term.statements),
    })),
    obligations: (overview?.obligations || []).map((obligation) => ({
      who: obligation.who,
      what: obligation.what,
      timing: obligation.timing,
      consequence: obligation.consequence,
      statements: verifiedStatements(obligation.statements),
    })),
    dates: (overview?.key_dates || []).map((date) => ({
      title: date.title,
      date: date.date,
      kind: date.timing_kind,
      description: date.description,
    })),
    risks: topRisks(review?.risks),
    missing: (review?.missing || []).map((item) => ({
      title: item.title,
      whyItMatters: item.why_it_matters,
      questionToAsk: item.question_to_ask,
    })),
    inconsistencies: (review?.inconsistencies || []).map((entry) => ({
      title: entry.title,
      explanation: entry.explanation,
      statements: verifiedStatements(entry.statements),
    })),
    lawReferences: (lawReferences || []).map((reference) => ({
      act: reference.act,
      section: reference.section,
      raw: reference.raw,
    })),
    questions: (answers || [])
      .filter((answer) => answer.answer_type !== 'out_of_scope')
      .map((answer) => ({
        question: answer.question,
        answered: answer.answer_type === 'direct' || answer.answer_type === 'interpretation',
        statements: verifiedStatements(answer.statements),
        needsProfessional: answer.needs_professional,
        questionsForProfessional: answer.questions_for_professional || [],
      })),
    factsToHaveReady: checklist?.facts_to_have_ready || [],
    documentsToBring: checklist?.documents_to_bring || [],
    verification: totals([overview?.verification, review?.verification, ...(answers || []).map((a) => a.verification)]),
  };
}

/**
 * Keep only statements with at least one verified citation.
 *
 * Verification already removed the rest, so this is a second guard: the brief
 * is the document a person may rely on, and a slip here is the worst kind.
 *
 * @param {object[]} list Statements.
 * @returns {object[]} `{ text, citations }` for the verified ones.
 */
export function verifiedStatements(list) {
  return (list || [])
    .filter((statement) => (statement.citations || []).some((citation) => citation.verified))
    .map((statement) => ({
      text: statement.text,
      kind: statement.kind,
      citations: (statement.citations || [])
        .filter((citation) => citation.verified)
        .map((citation) => ({ clauseId: citation.clause_id, quote: citation.quote })),
    }));
}

/**
 * Order risks so the most serious come first.
 *
 * @param {object[]} risks The risks.
 * @param {number} [limit] How many to include.
 * @returns {object[]} The top risks.
 */
export function topRisks(risks, limit = 8) {
  const order = { high: 0, medium: 1, low: 2 };
  return [...(risks || [])]
    .sort((a, b) => (order[a.severity] ?? 3) - (order[b.severity] ?? 3))
    .slice(0, limit)
    .map((risk) => ({
      title: risk.title,
      severity: risk.severity,
      explanation: risk.explanation,
      questionToAsk: risk.question_to_ask,
      statements: verifiedStatements(risk.statements),
    }));
}

/**
 * Sum several verification reports into one.
 *
 * @param {object[]} reports The reports, which may contain nulls.
 * @returns {{total: number, verified: number, removed: object[]}} The totals.
 */
export function totals(reports) {
  const present = (reports || []).filter(Boolean);
  return {
    total: present.reduce((sum, report) => sum + (report.total || 0), 0),
    verified: present.reduce((sum, report) => sum + (report.verified || 0), 0),
    removed: present.flatMap((report) => report.removed || []),
  };
}

/**
 * Check whether there is enough to be worth handing over.
 *
 * @param {object} brief A built brief.
 * @returns {boolean} True when the brief has content.
 */
export function isUseful(brief) {
  return (
    brief.summary.length > 0 ||
    brief.risks.length > 0 ||
    brief.questions.length > 0 ||
    brief.keyTerms.length > 0
  );
}
