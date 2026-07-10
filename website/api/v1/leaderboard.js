const { readSubmissions, scorePayload, sendJson } = require('../_submissions');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') return sendJson(res, 204, {}, {}, req);
  if (req.method !== 'GET') return sendJson(res, 405, { error: 'method not allowed' }, {}, req);

  try {
    const submissions = await readSubmissions();
    const entries = submissions
      .map(scorePayload)
      .sort((a, b) => b.overall_score - a.overall_score || b.pass_at_1 - a.pass_at_1);
    return sendJson(res, 200, { entries }, {}, req);
  } catch (error) {
    return sendJson(res, 500, { error: error.message || 'leaderboard unavailable' }, {}, req);
  }
};
