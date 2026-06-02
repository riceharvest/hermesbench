const { readCommunitySubmissions, scorePayload, sendJson } = require('../_submissions');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') return sendJson(res, 204, {});
  if (req.method !== 'GET') return sendJson(res, 405, { error: 'method not allowed' });

  try {
    const submissions = await readCommunitySubmissions();
    const entries = submissions
      .map((payload) => ({ ...scorePayload(payload), official: false, classification: 'community' }))
      .sort((a, b) => b.overall_score - a.overall_score || b.pass_at_1 - a.pass_at_1);
    return sendJson(res, 200, { entries, classification: 'community' });
  } catch (error) {
    return sendJson(res, 500, { error: error.message || 'community leaderboard unavailable' });
  }
};
