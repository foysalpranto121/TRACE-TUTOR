// API service for the TRACE Tutor frontend, talking to Django through the Vite proxy.
//
// There is no mock/offline mode. This platform is a research instrument, so a request
// that fails has to look like a failure: silently substituting plausible sample data
// for a dead backend is how invented passages and invented scores end up on screen.
import { getToken, clearSession } from './session';

const API_BASE = '/api';

export class ApiError extends Error {
  constructor(message, status, fields, body) {
    super(message);
    this.status = status;
    this.fields = fields || {};
    // The whole parsed error body, for endpoints that return structured detail
    // alongside the message (e.g. which assessment papers are currently open).
    this.body = body || {};
  }
}

// Helper for HTTP requests. Every failure raises an ApiError for the caller to render.
async function fetchApi(endpoint, options = {}) {
  const token = getToken();
  // FormData bodies must set their own multipart boundary, so no JSON content-type there.
  const headers = {
    ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
    ...(token ? { Authorization: `Token ${token}` } : {}),
    ...options.headers,
  };

  try {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      ...options,
      headers,
    });
    if (!response.ok) {
      let detail = `${response.status} ${response.statusText}`;
      let body = {};
      try {
        body = await response.json();
        detail = body.error || body.detail || body.message || detail;
      } catch (_) {
        /* non-JSON error body */
      }
      if (response.status === 401 && token && /token|credentials/i.test(detail)) {
        clearSession();
        window.dispatchEvent(new CustomEvent('trace:session-expired'));
        detail = 'Your session has expired. Please sign in again.';
      }
      throw new ApiError(detail, response.status, body.fields, body);
    }
    return await response.json();
  } catch (error) {
    if (error instanceof ApiError) throw error;
    const msg = error.message === 'Failed to fetch'
      ? 'Backend server is not reachable (is Django running on port 8000?)'
      : error.message;
    throw new ApiError(msg, 0);
  }
}

// File downloads need the auth header, so they cannot be a plain <a href>: fetch the
// body, then hand the browser a blob URL. A failed export raises; it never hands back
// a placeholder file.
async function downloadFile(endpoint, fallbackName) {
  const token = getToken();
  let response;
  try {
    response = await fetch(`${API_BASE}${endpoint}`, {
      headers: token ? { Authorization: `Token ${token}` } : {},
    });
  } catch (_) {
    throw new ApiError('Backend server is not reachable (is Django running on port 8000?)', 0);
  }
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      detail = body.error || body.detail || detail;
    } catch (_) {
      /* non-JSON error body */
    }
    throw new ApiError(detail, response.status);
  }

  const disposition = response.headers.get('Content-Disposition') || '';
  const match = disposition.match(/filename="?([^";]+)"?/);
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = match ? match[1] : fallbackName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
  return { rows: Number(response.headers.get('X-Trace-Row-Count')) || 0, filename: link.download };
}

// Identity is no longer sent by the client. The server takes the participant and their
// arm from the authenticated token and the server-side profile, and ignores any
// user_id / username / arm in a request body.
export const apiService = {
  getDashboard: () => fetchApi('/dashboard/'),
  register: (registrationData) => fetchApi('/accounts/register/', { method: 'POST', body: JSON.stringify(registrationData) }),
  login: (identifier, password) => fetchApi('/accounts/login/', { method: 'POST', body: JSON.stringify({ identifier, password }) }),
  // Takes the token explicitly: logout clears local storage first, so by the time this
  // runs getToken() is already empty and the request would go out unauthenticated -
  // leaving the server-side token alive and the session revocable only by expiry.
  logout: (token) =>
    fetchApi('/accounts/logout/', {
      method: 'POST',
      headers: token ? { Authorization: `Token ${token}` } : {},
    }),
  me: () => fetchApi('/accounts/me/'),
  updateProfile: (patch) => fetchApi('/accounts/profile/', { method: 'PATCH', body: JSON.stringify(patch) }),
  uploadAvatar: (file) => {
    const body = new FormData();
    body.append('avatar', file);
    return fetchApi('/accounts/avatar/', { method: 'POST', body });
  },
  deleteAvatar: () => fetchApi('/accounts/avatar/', { method: 'DELETE' }),
  changePassword: (currentPassword, newPassword) =>
    fetchApi('/accounts/password/', { method: 'POST', body: JSON.stringify({ current_password: currentPassword, new_password: newPassword }) }),
  // Right of access: everything the platform holds about the caller.
  myData: () => fetchApi('/accounts/my-data/'),
  // Leave the study. Erases the participant's data server-side and revokes the token,
  // so the caller must clear the local session afterwards.
  withdraw: (password) => fetchApi('/accounts/withdraw/', { method: 'POST', body: JSON.stringify({ password }) }),
  queryTutor: (prompt, code, problemId, arm, extra = {}) =>
    fetchApi('/tutor/query/', { method: 'POST', body: JSON.stringify({ prompt, code, problem_id: problemId, arm, ...extra }) }),

  // Real compiler service (compile + run test cases, or syntax-check only)
  runCode: (language, code, testCases = [], mode = 'run') =>
    fetchApi('/code/run/', { method: 'POST', body: JSON.stringify({ language, code, test_cases: testCases, mode }) }),
  getCodeStatus: () => fetchApi('/code/status/'),
  getRagStatus: () => fetchApi('/curriculum/status/'),
  // Fire-and-forget: a dropped telemetry event must never break the page the student is on.
  logTelemetry: (eventType, eventData) =>
    fetchApi('/telemetry/log/', { method: 'POST', body: JSON.stringify({ event_type: eventType, event_data: eventData || {} }) })
      .catch(() => ({ status: 'skipped', logged: false })),
  getAssessmentItems: (type) => fetchApi(`/assessment/items/?type=${type}`),
  // The server persists the answers at once and grades in the background: the response
  // carries grading_status ('pending' | 'grading' | 'graded' | 'failed') and, once
  // graded, { score_pct, correct, total, results }. Poll getSubmission until it settles.
  submitExam: (examData) => fetchApi('/assessment/submit/', { method: 'POST', body: JSON.stringify(examData) }),
  getSubmission: (id) => fetchApi(`/assessment/submissions/${id}/`),
  getExpertQueue: () => fetchApi('/expert/reviews/'),
  submitExpertRating: (itemId, ratings, feedback) => fetchApi('/expert/rating/', { method: 'POST', body: JSON.stringify({ item_id: itemId, ratings, feedback }) }),
  getAdminStats: () => fetchApi('/admin/stats/'),
  // Streams the real per-participant dataset straight to the browser as a download.
  exportDataset: () => downloadFile('/admin/export/', 'trace_tutor_dataset.csv'),
  // The exact configuration behind the data - file it next to the export.
  downloadManifest: () => downloadFile('/admin/manifest/', 'trace_tutor_manifest.json'),
  
  // Student Code Submission Evaluation & Marking by Expert
  getStudentSubmissions: () => fetchApi('/expert/submissions/'),
  gradeSubmission: (submissionId, assignedMarks, feedback) => fetchApi('/expert/grade/', { method: 'POST', body: JSON.stringify({ submission_id: submissionId, assigned_marks: assignedMarks, feedback }) }),

  // Curriculum RAG Engine (staff only). The RAG inspector is a research tool, so a
  // failed retrieval surfaces as an error, never as plausible-looking sample passages.
  searchCurriculum: (query, language) => fetchApi('/curriculum/search/', { method: 'POST', body: JSON.stringify({ query, language }) }),
  ingestCurriculum: (opts = {}) => fetchApi('/curriculum/ingest/', { method: 'POST', body: JSON.stringify(opts) }),
  getPassages: (language) => fetchApi(`/curriculum/passages/${language ? `?language=${language}` : ''}`),
};
