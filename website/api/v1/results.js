const {
  readBody,
  sendJson,
  validateSubmission,
  sanitizeResult,
  persistSubmission,
} = require('../_submissions');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') return sendJson(res, 204, {});
  if (req.method !== 'POST') return sendJson(res, 405, { error: 'method not allowed' });

  try {
    const payload = await readBody(req);
    const result = sanitizeResult(validateSubmission(payload));
    const persisted = await persistSubmission(result);
    return sendJson(res, 202, { run_id: result.run_id, accepted: true, persisted });
  } catch (error) {
    return sendJson(res, 400, { error: error.message || 'invalid submission' });
  }
};
