const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Readable } = require('node:stream');

process.env.HERMESBENCH_STORE_PATH = path.join(os.tmpdir(), `hermesbench-api-${process.pid}.jsonl`);
delete process.env.BLOB_READ_WRITE_TOKEN;

function mockReq(method, body) {
  const req = Readable.from(body ? [JSON.stringify(body)] : []);
  req.method = method;
  req.headers = { 'content-type': 'application/json' };
  return req;
}

function mockRes() {
  const headers = {};
  return {
    statusCode: 200,
    setHeader(key, value) { headers[key.toLowerCase()] = value; },
    end(body = '') { this.body = body; },
    get json() { return this.body ? JSON.parse(this.body) : null; },
    headers,
  };
}

async function call(handler, method, body) {
  const res = mockRes();
  await handler(mockReq(method, body), res);
  return res;
}

(async () => {
  await fs.rm(process.env.HERMESBENCH_STORE_PATH, { force: true });
  const health = require('../api/health');
  const results = require('../api/v1/results');
  const leaderboard = require('../api/v1/leaderboard');

  const healthRes = await call(health, 'GET');
  assert.equal(healthRes.statusCode, 200);
  assert.equal(healthRes.json.ok, true);

  const payload = {
    schema_version: 'hermesbench.submission.v1',
    classification: 'unofficial',
    result: {
      schema_version: 'hermesbench.result.v1',
      run_id: 'api-smoke-run',
      suite: 'public-dev',
      agent: 'mock',
      model: 'mock-model',
      started_at: '2026-06-02T00:00:00Z',
      completed_at: '2026-06-02T00:00:01Z',
      metadata: {},
      submission_token: 'do-not-persist',
      results: [
        { task_id: 't1', category: 'smoke', status: 'passed', score: 1, passed: true, logs: { transcript: 'secret' } },
      ],
    },
  };

  const uploadRes = await call(results, 'POST', payload);
  assert.equal(uploadRes.statusCode, 202);
  assert.equal(uploadRes.json.accepted, true);
  assert.equal(uploadRes.json.run_id, 'api-smoke-run');

  const persisted = await fs.readFile(process.env.HERMESBENCH_STORE_PATH, 'utf8');
  assert(!persisted.includes('do-not-persist'));
  assert(!persisted.includes('transcript'));

  const leaderboardRes = await call(leaderboard, 'GET');
  assert.equal(leaderboardRes.statusCode, 200);
  assert.equal(leaderboardRes.json.entries[0].run_id, 'api-smoke-run');
  assert.equal(leaderboardRes.json.entries[0].overall_score, 1);

  console.log('api smoke ok');
})();
