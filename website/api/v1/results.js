const {
  readBody,
  sendJson,
  validateSubmission,
  sanitizeResult,
  enforceRateLimit,
  persistSubmission,
  submissionsEnabled,
} = require('../_submissions');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') return sendJson(res, 204, {}, {}, req);
  if (req.method !== 'POST') return sendJson(res, 405, { error: 'method not allowed' }, {}, req);
  if (!submissionsEnabled()) return sendJson(res, 403, { error: 'public submissions are currently paused' }, {}, req);

  try {
    const payload = await readBody(req);
    const result = sanitizeResult(validateSubmission(payload, req));
    await enforceRateLimit(req);
    const persisted = await persistSubmission(result);
    const responseBody = { run_id: result.run_id, accepted: true, persisted };
    if (persisted.duplicate) {
      responseBody.duplicate = true;
    }
    return sendJson(res, 202, responseBody, {}, req);
  } catch (error) {
    return sendJson(res, error.status || 400, { error: error.message || 'invalid submission' }, error.headers || {}, req);
  }
};
