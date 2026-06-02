const { sendJson, blobEnabled } = require('./_submissions');

module.exports = async function handler(req, res) {
  if (req.method === 'OPTIONS') return sendJson(res, 204, {});
  if (req.method !== 'GET') return sendJson(res, 405, { error: 'method not allowed' });
  return sendJson(res, 200, { ok: true, storage: blobEnabled() ? 'vercel-blob' : 'local-jsonl' });
};
