const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Readable } = require('node:stream');
const { withFixedDateNow } = require('./test-fixed-clock');

process.env.HERMESBENCH_STORE_PATH = path.join(os.tmpdir(), `hermesbench-api-${process.pid}.jsonl`);
process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH = path.join(os.tmpdir(), `hermesbench-rate-${process.pid}.json`);
delete process.env.BLOB_READ_WRITE_TOKEN;
delete process.env.HERMESBENCH_SUBMISSION_TOKEN;
delete process.env.HERMESBENCH_RATE_LIMIT_MAX;
delete process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS;
delete process.env.VERCEL_ENV;
process.env.HERMESBENCH_SUBMISSIONS_ENABLED = 'true';

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
      suite: 'hermes-core',
      agent: 'hermes',
      model: 'test-model',
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

  process.env.HERMESBENCH_SUBMISSIONS_ENABLED = 'false';
  const pausedRes = await call(results, 'POST', payload, { 'x-hermesbench-submission-token': 'secret-token' });
  assert.equal(pausedRes.statusCode, 403);
  assert.match(pausedRes.json.error, /submissions are currently paused/);
  process.env.HERMESBENCH_SUBMISSIONS_ENABLED = 'true';

  const persisted = await fs.readFile(process.env.HERMESBENCH_STORE_PATH, 'utf8');
  assert(!persisted.includes('do-not-persist'));
  assert(!persisted.includes('transcript'));

  const leaderboardRes = await call(leaderboard, 'GET');
  assert.equal(leaderboardRes.statusCode, 200);
  assert.equal(leaderboardRes.json.entries[0].run_id, 'api-smoke-run');
  assert.equal(leaderboardRes.json.entries[0].overall_score, 1);

  // --- Security hardening regression tests ---

  // CORS: Origin-aware allowlisting with Vary header
  {
    const reqOrigin = 'http://localhost:4173';
    const corsRes = await call(leaderboard, 'GET', null, { Origin: reqOrigin });
    assert.equal(corsRes.statusCode, 200);
    assert.equal(corsRes.headers['access-control-allow-origin'], reqOrigin);
    assert.equal(corsRes.headers['vary'], 'Origin');
  }
  {
    // Non-allowlisted origin falls back to default
    const corsRes = await call(leaderboard, 'GET', null, { Origin: 'http://evil.example.com' });
    assert.equal(corsRes.statusCode, 200);
    assert.equal(corsRes.headers['access-control-allow-origin'], 'https://www.benchcut.info');
  }
  {
    // No Origin header -> default
    const corsRes = await call(leaderboard, 'GET');
    assert.equal(corsRes.statusCode, 200);
    assert.equal(corsRes.headers['access-control-allow-origin'], 'https://www.benchcut.info');
  }
  {
    // CORS on POST (results endpoint)
    const corsRes = await call(results, 'OPTIONS', null, { Origin: 'http://localhost:4177' });
    assert.equal(corsRes.statusCode, 204);
    assert.equal(corsRes.headers['access-control-allow-origin'], 'http://localhost:4177');
  }

  // Official flag rejection: classification = 'official'
  {
    const officialPayload = {
      schema_version: 'hermesbench.submission.v1',
      classification: 'official',
      result: {
        schema_version: 'hermesbench.result.v1',
        run_id: 'official-classification-test',
        suite: 'hermes-core',
        agent: 'hermes',
        model: 'test-model',
        metadata: {},
        submission_token: 'secret-token',
        results: [{ task_id: 't1', category: 'smoke', status: 'passed', score: 1, passed: true }],
      },
    };
    const offRes = await call(results, 'POST', officialPayload, { 'x-hermesbench-submission-token': 'secret-token' });
    assert.equal(offRes.statusCode, 400);
    assert.match(offRes.json.error, /official flag is maintainer-reserved/);
  }

  // Official flag rejection: metadata.official = true
  {
    const officialPayload = {
      schema_version: 'hermesbench.submission.v1',
      classification: 'unofficial',
      result: {
        schema_version: 'hermesbench.result.v1',
        run_id: 'official-metadata-test',
        suite: 'hermes-core',
        agent: 'hermes',
        model: 'test-model',
        metadata: { official: true },
        submission_token: 'secret-token',
        results: [{ task_id: 't1', category: 'smoke', status: 'passed', score: 1, passed: true }],
      },
    };
    const offRes = await call(results, 'POST', officialPayload, { 'x-hermesbench-submission-token': 'secret-token' });
    assert.equal(offRes.statusCode, 400);
    assert.match(offRes.json.error, /official flag is maintainer-reserved/);
  }

  // Request body too large -> 413
  {
    const hugeBody = Buffer.alloc(2 * 1024 * 1024, 'x').toString('utf8');
    const hugeReq = Readable.from([hugeBody]);
    hugeReq.method = 'POST';
    hugeReq.headers = { 'content-type': 'application/json', 'x-hermesbench-submission-token': 'secret-token' };
    hugeReq.socket = { remoteAddress: '127.0.0.1' };
    const hugeRes = mockRes();
    await results(hugeReq, hugeRes);
    assert.equal(hugeRes.statusCode, 413);
    assert.match(hugeRes.json.error, /request body exceeds/);
  }

  // readBody must reject pre-parsed object body that exceeds MAX_BODY_BYTES
  {
    const { readBody } = require('../api/_submissions');
    const bigData = { data: 'x'.repeat(2 * 1024 * 1024) };
    const objReq = { method: 'POST', headers: {}, body: bigData, socket: { remoteAddress: '127.0.0.1' } };
    try {
      await readBody(objReq);
      assert.fail('expected ApiError for oversized pre-parsed body');
    } catch (error) {
      assert.equal(error.status, 413);
      assert.match(error.message, /request body exceeds/);
    }
    const bigString = '{"data":"' + 'x'.repeat(2 * 1024 * 1024) + '"}';
    const strReq = { method: 'POST', headers: {}, body: bigString, socket: { remoteAddress: '127.0.0.1' } };
    try {
      await readBody(strReq);
      assert.fail('expected ApiError for oversized string body');
    } catch (error) {
      assert.equal(error.status, 413);
      assert.match(error.message, /request body exceeds/);
    }
    console.log('readBody byte-cap enforcement for all input forms ok');
  }

  // sanitizeResult must strip arbitrary metadata fields and arbitrary task fields
  {
    const { sanitizeResult } = require('../api/_submissions');
    const dirtyResult = {
      run_id: 'sanitize-test',
      suite: 'hermes-core',
      agent: 'hermes',
      submission_token: 'should-not-persist',
      metadata: {
        official: false,
        reasoning_effort: 'low',
        arbitrary_secret: 'leaked',
        api_key: 'sk-leaked',
      },
      results: [
        {
          task_id: 't1',
          category: 'smoke',
          status: 'passed',
          score: 1,
          passed: true,
          logs: 'sensitive-transcript',
          arbitrary_task_field: 'should-be-removed',
        },
      ],
    };
    const sanitized = sanitizeResult(dirtyResult);
    assert.equal(sanitized.submission_token, undefined, 'submission_token must be removed');
    assert.equal(sanitized.metadata.arbitrary_secret, undefined, 'arbitrary metadata must be stripped');
    assert.equal(sanitized.metadata.api_key, undefined, 'sensitive metadata key must be stripped');
    assert.equal(sanitized.metadata.sanitized, true, 'sanitized marker must be present');
    assert.equal(sanitized.metadata.reasoning_effort, 'low', 'allowlisted metadata must be retained');
    assert.equal(sanitized.results.length, 1);
    assert.equal(sanitized.results[0].task_id, 't1', 'allowlisted task field must be retained');
    assert.equal(sanitized.results[0].arbitrary_task_field, undefined, 'arbitrary task field must be stripped');
    assert.equal(sanitized.results[0].logs, undefined, 'sensitive task field must be stripped');
    console.log('sanitizeResult field allowlisting ok');
  }

  // Payload bounds: too many tasks -> 413
  {
    const tooManyTasks = {
      schema_version: 'hermesbench.submission.v1',
      classification: 'unofficial',
      result: {
        schema_version: 'hermesbench.result.v1',
        run_id: 'too-many-tasks-test',
        suite: 'hermes-core',
        agent: 'hermes',
        model: 'test-model',
        metadata: {},
        submission_token: 'secret-token',
        results: Array.from({ length: 201 }, (_, i) => ({ task_id: `t${i}`, category: 'smoke', status: 'passed', score: 1, passed: true })),
      },
    };
    const boundRes = await call(results, 'POST', tooManyTasks, { 'x-hermesbench-submission-token': 'secret-token' });
    assert.equal(boundRes.statusCode, 413);
    assert.match(boundRes.json.error, /task count.*exceeds maximum/);
  }

  // Payload bounds: too many metadata keys -> 413
  {
    const meta = {};
    for (let i = 0; i < 21; i++) meta[`key${i}`] = 'value';
    const tooManyMeta = {
      schema_version: 'hermesbench.submission.v1',
      classification: 'unofficial',
      result: {
        schema_version: 'hermesbench.result.v1',
        run_id: 'too-many-meta-test',
        suite: 'hermes-core',
        agent: 'hermes',
        model: 'test-model',
        metadata: meta,
        submission_token: 'secret-token',
        results: [{ task_id: 't1', category: 'smoke', status: 'passed', score: 1, passed: true }],
      },
    };
    const boundRes = await call(results, 'POST', tooManyMeta, { 'x-hermesbench-submission-token': 'secret-token' });
    assert.equal(boundRes.statusCode, 413);
    assert.match(boundRes.json.error, /metadata key count.*exceeds maximum/);
  }

  // Public field allowlist: leaderboard entries should only contain allowlisted fields
  {
    const lbRes = await call(leaderboard, 'GET');
    assert.equal(lbRes.statusCode, 200);
    const allowedFields = new Set(['run_id', 'agent', 'provider', 'model', 'suite', 'overall_score', 'pass_at_1', 'task_count', 'official', 'submitted_at']);
    for (const entry of lbRes.json.entries) {
      for (const key of Object.keys(entry)) {
        assert(allowedFields.has(key), `unexpected field '${key}' in leaderboard entry`);
      }
    }
  }

  // --- normalizeApiToFrontendShape regression assertions ---
  // Smoke-test the frontend's normalization function for live API responses.
  // Live API submissions must NOT be treated as capability evidence.
  function normalizeApiToFrontendShape(apiBody) {
    const entries = Array.isArray(apiBody?.entries) ? apiBody.entries : [];
    const liveNotice = 'Live leaderboard from the submissions API. Results are scored submissions, not official capability evidence.';
    const shape = {
      data_status: 'live_api',
      display_notice: liveNotice,
      capability_evidence: false,
      evidence_class: 'unofficial_submission',
      entries: entries.map((e) => ({ ...e, data_status: 'live_api', evidence_class: 'unofficial_submission', capability_evidence: false })),
      official: entries.filter((e) => e.official === true).map((e) => ({ ...e, data_status: 'live_api', evidence_class: 'unofficial_submission', capability_evidence: false })),
      unofficial: entries.filter((e) => e.official !== true).map((e) => ({ ...e, data_status: 'live_api', evidence_class: 'unofficial_submission', capability_evidence: false })),
      model_summaries: apiBody.model_summaries || null,
    };
    for (const group of ['entries', 'official', 'unofficial']) {
      for (const entry of shape[group] || []) {
        if (entry.capability_evidence == null) entry.capability_evidence = false;
        if (entry.evidence_class == null) entry.evidence_class = 'unofficial_submission';
      }
    }
    return shape;
  }
  const normalized = normalizeApiToFrontendShape(leaderboardRes.json);
  assert.equal(normalized.data_status, 'live_api');
  assert.equal(normalized.capability_evidence, false, 'live API normalized shape must NOT be capability_evidence');
  assert.equal(normalized.evidence_class, 'unofficial_submission', 'live API normalized shape must carry evidence_class');
  assert.equal(normalized.entries.length, 1);
  assert.equal(normalized.entries[0].run_id, 'api-smoke-run');
  assert.equal(normalized.entries[0].data_status, 'live_api');
  // Every entry must have capability_evidence=false and evidence_class set.
  for (const group of ['entries', 'official', 'unofficial']) {
    for (const entry of normalized[group] || []) {
      assert.equal(entry.capability_evidence, false, `entry in ${group} must not be capability evidence`);
      assert.equal(entry.evidence_class, 'unofficial_submission', `entry in ${group} must carry evidence_class`);
    }
  }
  console.log('live fetch normalization ok');

  process.env.HERMESBENCH_RATE_LIMIT_MAX = '1';
  process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS = '60';
  await withFixedDateNow(1_800_059_998_999, async () => {
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
  });
  delete process.env.HERMESBENCH_RATE_LIMIT_MAX;
  delete process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS;

  console.log('api smoke ok');
})().then(async () => {

// --- Additional regression tests ---

  const results = require('../api/v1/results');
  const { validateSubmission, tokenFromRequest } = require('../api/_submissions');

  let failures = 0;
  let total = 0;
  function check(label, ok) {
    total++;
    if (!ok) { console.error('FAIL:', label); failures++; }
    else console.log('PASS:', label);
  }

  // Token resolution: header is accepted
  {
    const token = tokenFromRequest(
      { headers: { 'x-hermesbench-submission-token': 'header-token' }, socket: { remoteAddress: '127.0.0.1' } },
    );
    check('token: header works', token === 'header-token');
  }

  // Token resolution: Bearer auth works
  {
    const token = tokenFromRequest(
      { headers: { authorization: 'Bearer bearer-token' }, socket: { remoteAddress: '127.0.0.1' } },
    );
    check('token: Bearer auth works', token === 'bearer-token');
  }

  // Token resolution: body tokens are rejected
  {
    const token = tokenFromRequest(
      { headers: {}, socket: { remoteAddress: '127.0.0.1' } },
    );
    check('token: body fallback rejected', token === null);
  }

  // Token resolution: no token anywhere -> empty string
  {
    const token = tokenFromRequest(
      { headers: {}, socket: { remoteAddress: '127.0.0.1' } },
    );
    check('token: empty when no token anywhere', token === null);
  }

  // mock agent submission -> 400
  {
    const mockPayload = {
      schema_version: 'hermesbench.submission.v1',
      classification: 'unofficial',
      result: {
        schema_version: 'hermesbench.result.v1',
        run_id: 'mock-agent-test',
        suite: 'test',
        agent: 'mock',
        metadata: {},
        submission_token: 'secret-token',
        results: [{ task_id: 't1', category: 'smoke', status: 'passed', score: 1, passed: true }],
      },
    };
    const response = mockRes();
    await results(mockReq('POST', mockPayload, { 'x-hermesbench-submission-token': 'secret-token' }), response);
    check('mock agent submission -> 400', response.statusCode === 400 && /mock agent/.test(response.json.error));
  }

  // Malformed JSON body -> parse error caught by results handler
  {
    const malformedReq = Readable.from(['{"bad json']);
    malformedReq.method = 'POST';
    malformedReq.headers = { 'content-type': 'application/json', 'x-hermesbench-submission-token': 'secret-token' };
    malformedReq.socket = { remoteAddress: '127.0.0.1' };
    const malformedRes = mockRes();
    await results(malformedReq, malformedRes);
    check('malformed JSON -> error response', malformedRes.statusCode >= 400);
  }

  // Missing schema_version -> 400
  {
    const noSchema = {
      run_id: 'no-schema-test',
      suite: 'test',
      agent: 'hermes',
      metadata: {},
      submission_token: 'secret-token',
      results: [{ task_id: 't1', category: 'smoke', status: 'passed', score: 1, passed: true }],
    };
    const noSchemaRes = mockRes();
    await results(mockReq('POST', { schema_version: 'hermesbench.submission.v1', classification: 'unofficial', result: noSchema }, { 'x-hermesbench-submission-token': 'secret-token' }), noSchemaRes);
    check('missing schema_version -> 400', noSchemaRes.statusCode === 400);
  }

  // Missing run_id -> 400
  {
    const noRunId = {
      schema_version: 'hermesbench.result.v1',
      suite: 'test',
      agent: 'hermes',
      metadata: {},
      submission_token: 'secret-token',
      results: [{ task_id: 't1', category: 'smoke', status: 'passed', score: 1, passed: true }],
    };
    const noRunIdRes = mockRes();
    await results(mockReq('POST', { schema_version: 'hermesbench.submission.v1', classification: 'unofficial', result: noRunId }, { 'x-hermesbench-submission-token': 'secret-token' }), noRunIdRes);
    check('missing run_id -> 400', noRunIdRes.statusCode === 400);
  }

  // Different run_ids with same content are both accepted (no false-positive conflict)
  {
    const payloadA = {
      schema_version: 'hermesbench.submission.v1',
      classification: 'unofficial',
      result: {
        schema_version: 'hermesbench.result.v1',
        run_id: 'unique-a-' + Date.now(),
        suite: 'test',
        agent: 'hermes',
        model: 'test',
        metadata: {},
        submission_token: 'secret-token',
        results: [{ task_id: 't1', category: 'smoke', status: 'passed', score: 1.0, passed: true }],
      },
    };
    const payloadB = { ...payloadA, result: { ...payloadA.result, run_id: 'unique-b-' + Date.now() } };
    const aRes = mockRes();
    await results(mockReq('POST', payloadA, {
      'x-hermesbench-submission-token': 'secret-token',
      'x-forwarded-for': '203.0.113.20',
    }), aRes);
    const bRes = mockRes();
    await results(mockReq('POST', payloadB, {
      'x-hermesbench-submission-token': 'secret-token',
      'x-forwarded-for': '203.0.113.20',
    }), bRes);
    check('different run_ids both accepted', aRes.statusCode === 202 && bRes.statusCode === 202);
  }

  const allPassed = failures === 0;
  console.log(`\nadditional regression tests: ${total - failures}/${total} passed${allPassed ? '' : ` (${failures} FAILED)`}`);
  if (!allPassed) process.exitCode = 1;
});
