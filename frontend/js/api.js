/**
 * Calls to the NyayaLens API.
 *
 * Same origin, so there is no CORS and no credentials to manage. Errors arrive
 * as RFC 9457 problem details and are turned into an `ApiError` carrying the
 * user-safe message the server chose.
 */

const BASE = '/api/v1';

/** An error the API reported, carrying its problem-details fields. */
export class ApiError extends Error {
  /**
   * @param {string} message User-safe message.
   * @param {object} [problem] The full problem document.
   */
  constructor(message, problem = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = problem.status || 0;
    this.type = problem.type || '';
    this.title = problem.title || '';
    this.fields = problem.errors || [];
  }
}

/**
 * Turn a failed response into an `ApiError`.
 *
 * @param {Response} response The response.
 * @returns {Promise<ApiError>} The error to throw.
 */
async function toError(response) {
  let problem = {};
  try {
    problem = await response.json();
  } catch {
    problem = {};
  }
  problem.status = problem.status || response.status;
  return new ApiError(problem.detail || problem.title || 'Something went wrong.', problem);
}

/**
 * Send a request and parse the JSON response.
 *
 * @param {string} path Path under the API prefix.
 * @param {object} [options] `fetch` options, plus an optional `json` body.
 * @returns {Promise<object>} The parsed response.
 */
export async function request(path, options = {}) {
  const { json, ...rest } = options;
  const init = { ...rest, headers: { Accept: 'application/json', ...(rest.headers || {}) } };
  if (json !== undefined) {
    init.method = init.method || 'POST';
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(json);
  }

  let response;
  try {
    response = await fetch(`${BASE}${path}`, init);
  } catch (cause) {
    throw new ApiError('NyayaLens could not be reached. Check your connection and try again.', {
      status: 0,
      type: 'network',
      cause,
    });
  }
  if (!response.ok) throw await toError(response);
  if (response.status === 204) return {};
  return response.json();
}

/**
 * Send a request and return the response body as a blob, for downloads.
 *
 * @param {string} path Path under the API prefix.
 * @param {object} json Request body.
 * @returns {Promise<{blob: Blob, filename: string}>} The file and its name.
 */
export async function download(path, json) {
  const response = await fetch(`${BASE}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(json),
  });
  if (!response.ok) throw await toError(response);
  return {
    blob: await response.blob(),
    filename: filenameFrom(response.headers.get('Content-Disposition')),
  };
}

/**
 * Read the file name out of a `Content-Disposition` header.
 *
 * @param {string|null} header The header value.
 * @returns {string} The file name, or an empty string.
 */
export function filenameFrom(header) {
  if (!header) return '';
  const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(header);
  return match ? decodeURIComponent(match[1]) : '';
}

export const api = {
  /** @returns {Promise<object>} Deployment metadata and feature flags. */
  meta: () => request('/meta'),

  /** @returns {Promise<object[]>} The built-in samples. */
  samples: () => request('/samples'),

  /**
   * @param {string} id Sample id.
   * @returns {Promise<object>} The ingested sample.
   */
  sample: (id) => request(`/samples/${encodeURIComponent(id)}`),

  /**
   * @param {File} file The chosen file.
   * @returns {Promise<object>} The ingested document.
   */
  upload(file) {
    const form = new FormData();
    form.append('file', file);
    form.append('title', file.name);
    return request('/documents', { method: 'POST', body: form });
  },

  /**
   * @param {string} text Pasted document text.
   * @param {string} [title] Optional title.
   * @returns {Promise<object>} The ingested document.
   */
  paste: (text, title = '') => request('/documents/text', { json: { text, title } }),

  /**
   * @param {object} body Document and audience.
   * @returns {Promise<object>} The overview.
   */
  overview: (body) => request('/analysis/overview', { json: body }),

  /**
   * @param {object} body Document and audience.
   * @returns {Promise<object>} The review.
   */
  review: (body) => request('/analysis/review', { json: body }),

  /**
   * @param {object} body Document, audience, question and history.
   * @returns {Promise<object>} The answer.
   */
  ask: (body) => request('/qa', { json: body }),

  /**
   * @param {object} body Two documents and a mode.
   * @returns {Promise<object>} The comparison.
   */
  compare: (body) => request('/compare', { json: body }),

  /**
   * @param {object} body Document, audience and a scenario.
   * @returns {Promise<object>} The what-if result.
   */
  scenario: (body) => request('/scenarios', { json: body }),

  /**
   * @param {string} docType The document type.
   * @returns {Promise<object>} The curated checklist.
   */
  checklist: (docType) => request(`/checklists/${encodeURIComponent(docType)}`),

  /** @returns {Promise<object[]>} General meanings for legal terms. */
  glossary: () => request('/glossary'),

  /**
   * @param {object} [params] `doc_type`, `situation` and `contextual`.
   * @returns {Promise<object[]>} Help directory entries.
   */
  resources(params = {}) {
    const query = new URLSearchParams();
    if (params.docType) query.set('doc_type', params.docType);
    for (const key of params.situations || []) query.append('situation', key);
    if (params.contextual) query.set('contextual', 'true');
    const suffix = query.toString();
    return request(`/resources${suffix ? `?${suffix}` : ''}`);
  },

  /**
   * @param {string} query What the user typed.
   * @returns {Promise<object>} Mappings, suggestions and sources.
   */
  lawLookup: (query) => request(`/laws/lookup?q=${encodeURIComponent(query)}`),

  /**
   * @param {object} body Old and new provision references.
   * @returns {Promise<object>} Comparison-table data.
   */
  lawCompare: (body) => request('/laws/compare', { json: body }),

  /**
   * @param {string} kind `new` or `removed`.
   * @returns {Promise<object[]>} Notable changes.
   */
  lawChanges: (kind) => request(`/laws/changes?kind=${encodeURIComponent(kind)}`),

  /**
   * @param {object} body A general legal question and the reader's audience.
   * @returns {Promise<object>} Matched sections and a verified answer.
   */
  legalQA: (body) => request('/laws/qa', { json: body }),

  /** @returns {Promise<object[]>} Letter templates with their field schemas. */
  draftTemplates: () => request('/drafts/templates'),

  /**
   * @param {object} body Template id, document and verified results.
   * @returns {Promise<object>} Prefilled facts with their citations.
   */
  draftPrefill: (body) => request('/drafts/prefill', { json: body }),

  /**
   * @param {object} body Template id and confirmed facts.
   * @returns {Promise<object>} A document model plus the audit reports.
   */
  draftPreview: (body) => request('/drafts/preview', { json: body }),

  /**
   * @param {object} body What to export, and in which format.
   * @returns {Promise<{blob: Blob, filename: string}>} The file.
   */
  export: (body) => download('/exports', body),

  /**
   * @param {object} body Key dates to put in a calendar.
   * @returns {Promise<{blob: Blob, filename: string}>} The `.ics` file.
   */
  calendar: (body) => download('/calendar', body),

  /**
   * @param {string} documentHash The document's id.
   * @returns {Promise<object>} How many cached results were dropped.
   */
  clearCache: (documentHash) =>
    request(`/cache/${encodeURIComponent(documentHash)}`, { method: 'DELETE' }),
};
