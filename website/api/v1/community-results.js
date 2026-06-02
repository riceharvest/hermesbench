const {
  readBody,
  sendJson,
  validateCommunitySubmission,
  sanitizeResult,
  enforceRateLimit,
  persistCommunitySubmission,
} = require('../_submissions');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') return sendJson(res, 204, {});
  if (req.method !== 'POST') return sendJson(res, 405, { error: 'method not allowed' });

  try {
    const payload = await readBody(req);
    const result = sanitizeResult(validateCommunitySubmission(payload));
    await enforceRateLimit(req);
    const persisted = await persistCommunitySubmission(result);
    return sendJson(res, 202, {
      run_id: result.run_id,
      accepted: true,
      classification: 'community',
      persisted,
    });
  } catch (error) {
    return sendJson(res, error.status || 400, { error: error.message || 'invalid submission' }, error.headers || {});
  }
};
