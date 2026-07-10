const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const { Readable } = require('node:stream');
const test = require('node:test');

// --- Isolated per-test storage ---
const storePath = path.join(os.tmpdir(), `hermesbench-store-hardening-${process.pid}.jsonl`);
const rateLimitStorePath = path.join(os.tmpdir(), `hermesbench-rate-hardening-${process.pid}.json`);

process.env.HERMESBENCH_STORE_PATH = storePath;
process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH = rateLimitStorePath;
process.env.HERMESBENCH_SUBMISSION_TOKEN = 'hardening-test-token';
delete process.env.BLOB_READ_WRITE_TOKEN;
delete process.env.VERCEL;
delete process.env.VERCEL_ENV;

// Mock for results handler
const { persistSubmission, readSubmissions, submissionBlobPath, blobEnabled } = require('../api/_submissions');

// Helper: create a minimal valid result object
function makeResult(runId, overrides = {}) {
  return {
    schema_version: 'hermesbench.result.v1',
    run_id: runId,
    suite: 'test-suite',
    agent: 'test-agent',
    model: 'test-model',
    metadata: {},
    results: [
      { task_id: 't1', category: 'test', status: 'passed', score: 1.0, passed: true },
    ],
    ...overrides,
  };
}

// Helper: mock HTTP req/res for the results handler
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

// ========================================================================
// Storage Hardening Tests
// ========================================================================

test('submissionBlobPath produces deterministic, hash-prefixed paths (unguessable without token)', async () => {
  // Same run_id + same token → same path
  const r1 = makeResult('test-run-001');
  const p1 = submissionBlobPath(r1);
  const p2 = submissionBlobPath(r1);
  assert.equal(p1, p2, 'deterministic for same run_id + token');

  // Path starts with prefix and contains a hash component
  assert(p1.startsWith('submissions/'), 'must have submissions/ prefix');
  const filename = p1.slice('submissions/'.length);
  assert.match(filename, /^[0-9a-f]{16}-/, 'filename must have 16-char hex hash prefix');
  assert(filename.endsWith('.json'), 'must end with .json');
  assert(filename.includes('test-run-001'), 'must include sanitized run_id');

  // Different run_id → different path
  const r2 = makeResult('test-run-002');
  const p3 = submissionBlobPath(r2);
  assert.notEqual(p1, p3, 'different run_id must produce different path');
});

test('persistSubmission rejects duplicate run_id with conflicting content (409)', async () => {
  await fs.rm(storePath, { force: true });

  const result1 = makeResult('conflict-run', { score: 1.0 });
  const result2 = makeResult('conflict-run', { score: 0.5 }); // same run_id, different content

  // First submission should succeed
  const first = await persistSubmission(result1);
  assert.equal(first.store, 'local-jsonl');
  assert.equal(first.conflict, false);
  assert.equal(first.duplicate, undefined);

  // Second submission with different content should get 409
  await assert.rejects(
    () => persistSubmission(result2),
    (err) => {
      assert.equal(err.status, 409);
      assert.match(err.message, /duplicate run_id.*conflicting content/);
      return true;
    },
  );
});

test('persistSubmission accepts identical re-submission (idempotent 202 with duplicate: true)', async () => {
  await fs.rm(storePath, { force: true });

  const result = makeResult('idempotent-run', { score: 1.0 });

  // First submission
  const first = await persistSubmission(result);
  assert.equal(first.store, 'local-jsonl');
  assert.equal(first.conflict, false);
  assert.equal(first.duplicate, undefined);

  // Identical re-submission
  const second = await persistSubmission(result);
  assert.equal(second.store, 'local-jsonl');
  assert.equal(second.conflict, false);
  assert.equal(second.duplicate, true, 'identical re-submission must set duplicate: true');

  // Only one entry in the store
  const submissions = await readSubmissions();
  const matching = submissions.filter((s) => s.run_id === 'idempotent-run');
  assert.equal(matching.length, 1, 'identical re-submission must not create duplicate DB entry');
});

test('Different run_ids with same content are both accepted (no false-positive conflict)', async () => {
  await fs.rm(storePath, { force: true });

  const r1 = makeResult('unique-run-a');
  const r2 = makeResult('unique-run-b');

  const first = await persistSubmission(r1);
  assert.equal(first.conflict, false);

  const second = await persistSubmission(r2);
  assert.equal(second.conflict, false);
  assert.equal(second.duplicate, undefined);
});

test('persistSubmission fails closed with 503 when VERCEL=1 and Blob is not configured', async () => {
  process.env.VERCEL = '1';
  delete process.env.BLOB_READ_WRITE_TOKEN; // ensure Blob is NOT enabled

  const result = makeResult('vercel-no-blob-run');

  await assert.rejects(
    () => persistSubmission(result),
    (err) => {
      assert.equal(err.status, 503);
      assert.match(err.message, /submission storage.*not configured/);
      return true;
    },
  );

  delete process.env.VERCEL;
});

test('persistSubmission works with local store (no VERCEL flag) when Blob is not configured', async () => {
  await fs.rm(storePath, { force: true });
  delete process.env.VERCEL;
  delete process.env.BLOB_READ_WRITE_TOKEN;

  const result = makeResult('local-only-run');
  const persisted = await persistSubmission(result);
  assert.equal(persisted.store, 'local-jsonl');
  assert.equal(persisted.conflict, false);

  // Verify it was persisted
  const submissions = await readSubmissions();
  const match = submissions.find((s) => s.run_id === 'local-only-run');
  assert(match, 'submission must be readable from store');
});

test('submission response in results.js includes duplicate flag for idempotent re-submission', async () => {
  await fs.rm(storePath, { force: true });

  const handler = require('../api/v1/results');

  const payload = {
    schema_version: 'hermesbench.submission.v1',
    classification: 'unofficial',
    result: makeResult('response-dupe-test'),
  };

  // Submit once
  const res1 = mockRes();
  const req1 = mockReq('POST', payload, { 'x-hermesbench-submission-token': 'hardening-test-token' });
  await handler(req1, res1);
  assert.equal(res1.statusCode, 202);
  assert.equal(res1.json.accepted, true);
  assert.equal(res1.json.duplicate, undefined, 'first submission must not have duplicate flag');

  // Submit identical again
  const res2 = mockRes();
  const req2 = mockReq('POST', payload, { 'x-hermesbench-submission-token': 'hardening-test-token' });
  await handler(req2, res2);
  assert.equal(res2.statusCode, 202);
  assert.equal(res2.json.accepted, true);
  assert.equal(res2.json.duplicate, true, 'identical re-submission must include duplicate: true');
});

test('results.js handler returns 409 for conflicting duplicate run_id', async () => {
  await fs.rm(storePath, { force: true });

  const handler = require('../api/v1/results');

  const makePayload = (score) => ({
    schema_version: 'hermesbench.submission.v1',
    classification: 'unofficial',
    result: makeResult('handler-conflict', { score }),
  });

  // Submit first
  const res1 = mockRes();
  const req1 = mockReq('POST', makePayload(1.0), { 'x-hermesbench-submission-token': 'hardening-test-token' });
  await handler(req1, res1);
  assert.equal(res1.statusCode, 202);

  // Submit conflicting (different score = different content)
  const res2 = mockRes();
  const req2 = mockReq('POST', makePayload(0.5), { 'x-hermesbench-submission-token': 'hardening-test-token' });
  await handler(req2, res2);
  assert.equal(res2.statusCode, 409);
  assert.match(res2.json.error, /duplicate run_id.*conflicting content/);
});

test('blobEnabled returns false when token is unset', () => {
  // This is the isolated env, so BLOB_READ_WRITE_TOKEN is already deleted
  assert.equal(blobEnabled(), false);
});

test('persistSubmission detects identical vs conflicting after identical-then-different sequence', async () => {
  await fs.rm(storePath, { force: true });

  const runId = 'sequence-run';
  const base = makeResult(runId);

  // Submit original
  const first = await persistSubmission(base);
  assert.equal(first.duplicate, undefined);

  // Submit identical
  const second = await persistSubmission(base);
  assert.equal(second.duplicate, true, 'identical re-submit must be idempotent');

  // Conflicting (same run_id, different content)
  const conflict = makeResult(runId, { score: 0.0, results: [
    { task_id: 't1', category: 'test', status: 'failed', score: 0.0, passed: false },
  ]});
  await assert.rejects(
    () => persistSubmission(conflict),
    (err) => {
      assert.equal(err.status, 409);
      assert.match(err.message, /duplicate run_id/);
      return true;
    },
  );
});

// Mock module-level globals for Blob-code-path testing
// We mock @vercel/blob by substituting the module before requiring.
// Each mock is reset between tests via a fresh require.

function mockBlobClient(overrides = {}) {
  const defaults = {
    put: async () => ({ url: 'https://mock.blob.test/store.json', pathname: 'store.json', etag: 'mock-etag' }),
    head: async () => ({ url: 'https://mock.blob.test/store.json', etag: 'mock-etag', pathname: 'store.json', size: 100, contentType: 'application/json', uploadedAt: new Date() }),
    get: async () => ({ stream: (async function* () { yield '{"run_id_hash":"abc","run_id":"mock","suite":"test","agent":"mock-agent","results":[]}'; })() }),
    list: async () => ({ blobs: [{ url: 'https://mock.blob.test/list.json', pathname: 'list.json' }] }),
    BlobPreconditionFailedError: class BlobPreconditionFailedError extends Error {
      constructor(msg) { super(msg || 'Precondition failed'); this.name = 'BlobPreconditionFailedError'; }
    },
  };
  const mock = { ...defaults, ...overrides };

  // Override get to return a readable-like stream
  return mock;
}

// Restore the real module cache so we can require again with env overrides
function clearBlobModuleCache() {
  const cacheKey = require.resolve('@vercel/blob');
  delete require.cache[cacheKey];
}

test('submissionBlobPath changes when token changes', () => {
  const result = makeResult('token-test');
  const tokenWas = process.env.HERMESBENCH_SUBMISSION_TOKEN;

  // Path with current token
  const pathWithToken = submissionBlobPath(result);

  // Change token
  process.env.HERMESBENCH_SUBMISSION_TOKEN = 'different-token';
  const pathWithDifferentToken = submissionBlobPath(result);

  assert.notEqual(pathWithToken, pathWithDifferentToken,
    'different token must produce different blob path');

  // Restore
  process.env.HERMESBENCH_SUBMISSION_TOKEN = tokenWas;
});

test('local store empty file handled gracefully on first read', async () => {
  await fs.rm(storePath, { force: true });
  // Ensure file doesn't exist
  const exists = await fs.stat(storePath).then(() => true, () => false);
  assert.equal(exists, false);

  const submissions = await readSubmissions();
  assert.deepEqual(submissions, []);
});

test('sanitizeResult strips run_id_hash from stored result', async () => {
  const { sanitizeResult } = require('../api/_submissions');

  const dirty = makeResult('sanitize-hash-test');
  dirty.run_id_hash = 'abc123shouldnotappear';

  const sanitized = sanitizeResult(dirty);
  assert.equal(sanitized.run_id_hash, undefined, 'run_id_hash must be stripped by sanitizeResult');
});

test('Blob path is submissionBlobPath, not simple submissionPath (production consistency)', () => {
  const { submissionBlobPath, submissionPath } = require('../api/_submissions');

  const r = makeResult('path-consistency');
  const blobPath = submissionBlobPath(r);
  const simplePath = submissionPath(r);

  // blobPath must include the hash prefix
  const blobFilename = blobPath.slice('submissions/'.length);
  const simpleFilename = simplePath.slice('submissions/'.length);
  assert.notEqual(blobFilename, simpleFilename, 'blob path must differ from simple path via hash prefix');
  assert(blobFilename.includes(simpleFilename), 'blob filename must contain the safe-run-id segment');
});

// Clean up temp files after all tests
process.on('exit', () => {
  fs.rm(storePath, { force: true }).catch(() => {});
  fs.rm(rateLimitStorePath, { force: true }).catch(() => {});
});

// ========================================================================
// Blob-code-path tests (mocked Blob client, no real credentials required)
// ========================================================================

// We test Blob-only logic by manipulating process.env and the require cache.
// These tests do NOT need real BLOB_READ_WRITE_TOKEN — the mock client is
// injected by clearing the require cache and overriding module-level vars.
//
// IMPORTANT: These tests verify the logic that runs on Vercel, but they
// do so with a fake in-memory blob. They are LOCAL SIMULATION, not a
// real Vercel deployment. Differences from production:
//   - No actual HTTP requests to Vercel Blob API
//   - No actual Vercel edge runtime behavior
//   - No actual token rotation or network failures
//   - Mock uses in-process function stubs

async function withBlobEnv(blobMock, fn) {
  const origBlobToken = process.env.BLOB_READ_WRITE_TOKEN;
  const origVercel = process.env.VERCEL;
  const origToken = process.env.HERMESBENCH_SUBMISSION_TOKEN;

  process.env.BLOB_READ_WRITE_TOKEN = 'mock-blob-token';
  process.env.VERCEL = '1';
  process.env.HERMESBENCH_SUBMISSION_TOKEN = 'mock-sub-token';

  // Stash real blobClient and inject mock
  const subs = require.cache[require.resolve('../api/_submissions')];
  const realBlobClient = subs?.exports?.blobClient;

  // Inject mock into the module's scope. We can patch blobClient directly
  // since the module exposes a mutable object.
  try {
    // We cannot directly modify the module's internal `blobClient` variable
    // from outside. Instead, use proxy: pre-clear the cache and reload with
    // a stub @vercel/blob.
    // Strategy: mock the module directly via require.cache injection.
    const blobMockPath = require.resolve('@vercel/blob');
    require.cache[blobMockPath] = {
      id: blobMockPath,
      filename: blobMockPath,
      loaded: true,
      exports: blobMock,
    };

    // Reload _submissions to pick up the mocked client
    delete require.cache[require.resolve('../api/_submissions')];
    const { persistSubmission, readSubmissions, blobEnabled: be } = require('../api/_submissions');

    await fn({ persistSubmission, readSubmissions, blobEnabled: be });
  } finally {
    // Restore env
    if (origBlobToken) process.env.BLOB_READ_WRITE_TOKEN = origBlobToken;
    else delete process.env.BLOB_READ_WRITE_TOKEN;
    if (origVercel) process.env.VERCEL = origVercel;
    else delete process.env.VERCEL;
    if (origToken) process.env.HERMESBENCH_SUBMISSION_TOKEN = origToken;
    else delete process.env.HERMESBENCH_SUBMISSION_TOKEN;

    // Restore real blob module
    delete require.cache[require.resolve('@vercel/blob')];
    delete require.cache[require.resolve('../api/_submissions')];
  }
}

test('blobEnabled: returns true with mock token and mock client', async () => {
  const mock = mockBlobClient();
  await withBlobEnv(mock, ({ blobEnabled }) => {
    assert.equal(blobEnabled(), true);
  });
});

test('blobEnabled: returns false when token is missing (even with mock client)', async () => {
  const mock = mockBlobClient();
  const origToken = process.env.BLOB_READ_WRITE_TOKEN;
  try {
    delete process.env.BLOB_READ_WRITE_TOKEN;
    const { blobEnabled } = require('../api/_submissions');
    assert.equal(blobEnabled(), false);
  } finally {
    if (origToken) process.env.BLOB_READ_WRITE_TOKEN = origToken;
    else delete process.env.BLOB_READ_WRITE_TOKEN;
  }
});

test('persistSubmission with mocked blob: first write succeeds', async () => {
  const storage = {};
  const mock = mockBlobClient({
    head: async () => null, // No existing blob
    put: async (pathname, body, opts) => {
      storage[pathname] = body;
      return { url: `https://mock/${pathname}`, pathname, etag: 'e1' };
    },
  });

  await withBlobEnv(mock, async ({ persistSubmission }) => {
    const result = makeResult('blob-first-write');
    const persisted = await persistSubmission(result);
    assert.equal(persisted.store, 'vercel-blob');
    assert.equal(persisted.conflict, false);
    assert.equal(persisted.duplicate, undefined);
  });
});

test('persistSubmission with mocked blob: identical re-submission is idempotent', async () => {
  let callCount = 0;
  const storage = {};
  const mock = mockBlobClient({
    head: async (path) => {
      if (storage[path]) {
        return { url: `https://mock/${path}`, etag: storage[path]?.etag || 'e1', pathname: path, size: 100, contentType: 'application/json', uploadedAt: new Date() };
      }
      return null;
    },
    get: async (path) => {
      const entry = storage[path];
      if (entry) {
        const { Readable } = require('stream');
        return { stream: Readable.from([entry.body]) };
      }
      return null;
    },
    put: async (pathname, body, opts) => {
      callCount++;
      storage[pathname] = { body, etag: 'e1' };
      return { url: `https://mock/${pathname}`, pathname, etag: 'e1' };
    },
  });

  await withBlobEnv(mock, async ({ persistSubmission }) => {
    const result = makeResult('blob-dup-test');
    const first = await persistSubmission(result);
    assert.equal(first.duplicate, undefined, 'first submission must not be duplicate');

    const second = await persistSubmission(result);
    assert.equal(second.duplicate, true, 'identical re-submission must be idempotent');
    assert.equal(callCount, 1, 'put must not be called for duplicate');
  });
});

test('persistSubmission with mocked blob: conflicting run_id gets 409', async () => {
  const storage = {};
  let existingBody = null;
  const mock = mockBlobClient({
    head: async (path) => {
      if (storage[path]) {
        return { url: `https://mock/${path}`, etag: storage[path]?.etag || 'e1', pathname: path, size: 100, contentType: 'application/json', uploadedAt: new Date() };
      }
      return null;
    },
    get: async (path) => {
      const entry = storage[path];
      if (entry) {
        const { Readable } = require('stream');
        return { stream: Readable.from([entry.body]) };
      }
      return null;
    },
    put: async (pathname, body, opts) => {
      storage[pathname] = { body, etag: 'e1' };
      existingBody = body;
      return { url: `https://mock/${pathname}`, pathname, etag: 'e1' };
    },
  });

  await withBlobEnv(mock, async ({ persistSubmission }) => {
    const result1 = makeResult('blob-conflict', { score: 1.0 });
    await persistSubmission(result1);

    const result2 = makeResult('blob-conflict', { score: 0.5 });
    await assert.rejects(
      () => persistSubmission(result2),
      (err) => {
        assert.equal(err.status, 409);
        assert.match(err.message, /duplicate run_id.*conflicting content/);
        return true;
      },
    );
  });
});

test('persistSubmission with mocked blob: VERCEL=1 with no Blob client fails 503', async () => {
  const orig = process.env.BLOB_READ_WRITE_TOKEN;
  const origVercel = process.env.VERCEL;
  const origToken = process.env.HERMESBENCH_SUBMISSION_TOKEN;
  try {
    delete process.env.BLOB_READ_WRITE_TOKEN;
    process.env.VERCEL = '1';
    process.env.HERMESBENCH_SUBMISSION_TOKEN = 'tok';

    // Clear module cache so blobClient is null
    delete require.cache[require.resolve('@vercel/blob')];
    delete require.cache[require.resolve('../api/_submissions')];

    const { persistSubmission } = require('../api/_submissions');
    const result = makeResult('blob-vercel-fail');

    await assert.rejects(
      () => persistSubmission(result),
      (err) => {
        assert.equal(err.status, 503);
        assert.match(err.message, /submission storage.*not configured/);
        return true;
      },
    );
  } finally {
    if (orig) process.env.BLOB_READ_WRITE_TOKEN = orig;
    else delete process.env.BLOB_READ_WRITE_TOKEN;
    if (origVercel) process.env.VERCEL = origVercel;
    else delete process.env.VERCEL;
    if (origToken) process.env.HERMESBENCH_SUBMISSION_TOKEN = origToken;
    else delete process.env.HERMESBENCH_SUBMISSION_TOKEN;
    delete require.cache[require.resolve('@vercel/blob')];
    delete require.cache[require.resolve('../api/_submissions')];
  }
});

test('persistSubmission with mocked blob: concurrent first-write race resolved as idempotent', async () => {
  // Simulate: two requests race to create the same blob.
  // First put() succeeds, second put() gets BlobPreconditionFailedError,
  // handler re-reads and finds identical content → duplicate: true.
  let putCallCount = 0;
  const storage = {};

  const PreconditionError = class extends Error {
    constructor(m) { super(m || 'Precondition failed'); this.name = 'BlobPreconditionFailedError'; }
  };

  const mock = mockBlobClient({
    head: async (path) => {
      if (storage[path]) {
        return { url: `https://mock/${path}`, etag: storage[path]?.etag || 'e1', pathname: path, size: 100, contentType: 'application/json', uploadedAt: new Date() };
      }
      return null;
    },
    get: async (path) => {
      const entry = storage[path];
      if (entry) {
        const { Readable } = require('stream');
        return { stream: Readable.from([entry.body]) };
      }
      return null;
    },
    put: async (pathname, body, opts) => {
      putCallCount++;
      if (putCallCount === 1) {
        // First call succeeds
        storage[pathname] = { body, etag: 'e1' };
        return { url: `https://mock/${pathname}`, pathname, etag: 'e1' };
      }
      // Second call simulates race — blob already exists unexpectedly
      throw new PreconditionError();
    },
  });

  await withBlobEnv(mock, async ({ persistSubmission }) => {
    const result = makeResult('concurrent-race');

    // First write succeeds normally
    const first = await persistSubmission(result);
    assert.equal(first.store, 'vercel-blob');
    assert.equal(first.conflict, false);

    // Second write triggers race → re-reads and finds identical → duplicate
    const second = await persistSubmission(result);
    assert.equal(second.duplicate, true, 'race must result in idempotent acceptance');
  });
});
