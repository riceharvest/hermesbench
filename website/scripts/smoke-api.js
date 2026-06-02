const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Readable } = require('node:stream');

process.env.HERMESBENCH_STORE_PATH = path.join(os.tmpdir(), `hermesbench-api-${process.pid}.jsonl`);
process.env.HERMESBENCH_COMMUNITY_STORE_PATH = path.join(os.tmpdir(), `hermesbench-community-${process.pid}.jsonl`);
process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH = path.join(os.tmpdir(), `hermesbench-rate-${process.pid}.json`);
delete process.env.BLOB_READ_WRITE_TOKEN;
delete process.env.HERMESBENCH_SUBMISSION_TOKEN;
delete process.env.HERMESBENCH_RATE_LIMIT_MAX;
delete process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS;
delete process.env.VERCEL_ENV;

function mockReq(method, body, headers = {}) {
  const req = Readable.from(body ? [JSON.stringify(body)] : []);
  req.method = method;
  req.headers = { 'content-type': 'application/json', ...headers };
  req.socket = { remoteAddress: '127.0.0.1' };
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

async function call(handler, method, body, headers = {}) {
  const res = mockRes();
  await handler(mockReq(method, body, headers), res);
  return res;
}

(async () => {
  await fs.rm(process.env.HERMESBENCH_STORE_PATH, { force: true });
  const health = require('../api/health');
  const results = require('../api/v1/results');
  const communityResults = require('../api/v1/community-results');
  const leaderboard = require('../api/v1/leaderboard');
  const communityLeaderboard = require('../api/v1/community-leaderboard');

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

  process.env.VERCEL_ENV = 'production';
  const failClosedRes = await call(results, 'POST', payload);
  assert.equal(failClosedRes.statusCode, 503);
  assert.match(failClosedRes.json.error, /submission token is not configured/);
  delete process.env.VERCEL_ENV;

  process.env.HERMESBENCH_SUBMISSION_TOKEN = 'secret-token';
  const invalidTokenRes = await call(results, 'POST', payload, { 'x-hermesbench-submission-token': 'wrong-token' });
  assert.equal(invalidTokenRes.statusCode, 401);
  assert.match(invalidTokenRes.json.error, /submission token/);

  const uploadRes = await call(results, 'POST', payload, { 'x-hermesbench-submission-token': 'secret-token' });
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

  const communityPayload = { ...payload, result: { ...payload.result, run_id: 'community-smoke-run' } };
  delete communityPayload.result.submission_token;
  const communityUploadRes = await call(communityResults, 'POST', communityPayload, { 'x-forwarded-for': '198.51.100.8' });
  assert.equal(communityUploadRes.statusCode, 202);
  assert.equal(communityUploadRes.json.accepted, true);
  assert.equal(communityUploadRes.json.classification, 'community');
  assert.equal(communityUploadRes.json.persisted.store, 'community-jsonl');

  const mainAfterCommunity = await call(leaderboard, 'GET');
  assert(!mainAfterCommunity.json.entries.some((entry) => entry.run_id === 'community-smoke-run'));

  const communityBoardRes = await call(communityLeaderboard, 'GET');
  assert.equal(communityBoardRes.statusCode, 200);
  assert.equal(communityBoardRes.json.entries[0].run_id, 'community-smoke-run');
  assert.equal(communityBoardRes.json.entries[0].official, false);

  await fs.rm(process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH, { force: true });
  process.env.HERMESBENCH_RATE_LIMIT_MAX = '1';
  process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS = '60';
  const firstLimited = await call(results, 'POST', { ...payload, result: { ...payload.result, run_id: 'rate-one' } }, {
    'x-forwarded-for': '203.0.113.9',
    'x-hermesbench-submission-token': 'secret-token',
  });
  assert.equal(firstLimited.statusCode, 202);
  const secondLimited = await call(results, 'POST', { ...payload, result: { ...payload.result, run_id: 'rate-two' } }, {
    'x-forwarded-for': '203.0.113.9',
    'x-hermesbench-submission-token': 'secret-token',
  });
  assert.equal(secondLimited.statusCode, 429);
  assert.match(secondLimited.json.error, /rate limit/);
  assert(Number.parseInt(secondLimited.headers['retry-after'], 10) > 0);
  assert(Number.parseInt(secondLimited.headers['retry-after'], 10) <= 60);

  console.log('api smoke ok');
})();
