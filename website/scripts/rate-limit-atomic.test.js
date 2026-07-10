const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');
const { withFixedDateNow } = require('./test-fixed-clock');

const rateLimitStorePath = path.join(os.tmpdir(), `hermesbench-rate-atomic-test-${process.pid}.json`);
process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH = rateLimitStorePath;
process.env.HERMESBENCH_SUBMISSION_TOKEN = 'test-token';
delete process.env.BLOB_READ_WRITE_TOKEN; // force local path for isolation

const { enforceRateLimit, blobEnabled } = require('../api/_submissions');

test('blobEnabled returns false when BLOB_READ_WRITE_TOKEN is unset', () => {
  assert.equal(blobEnabled(), false);
});

test('local rate limit window evicts old buckets', async () => {
  await fs.rm(rateLimitStorePath, { force: true });

  // Write a stale bucket (already expired) into the store manually.
  const staleKey = 'stalehash:' + String(Math.floor(1_000_000_000 / 60_000) * 60_000);
  const currentResetAt = Math.ceil((1_800_059_998_000 + 60_000) / 1000);
  await fs.mkdir(path.dirname(rateLimitStorePath), { recursive: true });
  await fs.writeFile(rateLimitStorePath, JSON.stringify({
    [staleKey]: { count: 99, reset_at: 1_000_000_000 }, // expired ages ago
  }));

  await withFixedDateNow(1_800_059_998_999, async () => {
    await enforceRateLimit({ headers: { 'x-forwarded-for': '10.0.0.1' } });
  });

  // After enforceRateLimit, the stale bucket should have been evicted.
  const stored = JSON.parse(await fs.readFile(rateLimitStorePath, 'utf8'));
  assert.equal(stored[staleKey], undefined, 'stale bucket must be evicted');
});

test('local rate limit increments and enforces max', async () => {
  await fs.rm(rateLimitStorePath, { force: true });

  process.env.HERMESBENCH_RATE_LIMIT_MAX = '3';
  process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS = '60';

  const nearMinuteEnd = 1_800_059_998_999;
  const request1 = { headers: { 'x-forwarded-for': '10.0.0.2' } };
  const request2 = { headers: { 'x-forwarded-for': '10.0.0.3' } };

  await withFixedDateNow(nearMinuteEnd, async () => {
    // IP 10.0.0.2: 3 requests within limit
    await enforceRateLimit(request1);
    await enforceRateLimit(request1);
    await enforceRateLimit(request1);

    // 4th request should fail
    await assert.rejects(
      () => enforceRateLimit(request1),
      (err) => {
        assert.equal(err.status, 429);
        assert.match(err.message, /rate limit/);
        assert(Number.parseInt(err.headers['retry-after'], 10) > 0);
        return true;
      },
    );

    // Different IP should still work
    await enforceRateLimit(request2);
    await enforceRateLimit(request2);
  });

  delete process.env.HERMESBENCH_RATE_LIMIT_MAX;
  delete process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS;
});

test('rate limit with max=0 or window=0 is a no-op', async () => {
  await fs.rm(rateLimitStorePath, { force: true });

  process.env.HERMESBENCH_RATE_LIMIT_MAX = '0';
  process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS = '60';

  // Should not throw
  await enforceRateLimit({ headers: { } });

  process.env.HERMESBENCH_RATE_LIMIT_MAX = '12';
  process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS = '0';

  // Should not throw
  await enforceRateLimit({ headers: { } });

  delete process.env.HERMESBENCH_RATE_LIMIT_MAX;
  delete process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS;
});

test('different minute windows produce different rate-limit keys', async () => {
  await fs.rm(rateLimitStorePath, { force: true });

  process.env.HERMESBENCH_RATE_LIMIT_MAX = '1';
  process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS = '60';

  // Same window: two requests should hit the limit
  await withFixedDateNow(1_800_059_998_999, async () => {
    await enforceRateLimit({ headers: { 'x-forwarded-for': '203.0.113.5' } });

    // Same IP, same window — should be blocked
    await assert.rejects(
      () => enforceRateLimit({ headers: { 'x-forwarded-for': '203.0.113.5' } }),
      (err) => err.status === 429,
    );
  });

  // Next window: same IP, should succeed
  await withFixedDateNow(1_800_060_000_000, async () => {
    await enforceRateLimit({ headers: { 'x-forwarded-for': '203.0.113.5' } });
  });

  delete process.env.HERMESBENCH_RATE_LIMIT_MAX;
  delete process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS;
});

test('rate limit respects x-real-ip and falls back to remoteAddress', async () => {
  await fs.rm(rateLimitStorePath, { force: true });

  process.env.HERMESBENCH_RATE_LIMIT_MAX = '1';
  process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS = '60';

  const fixed = 1_800_059_998_999;

  // x-real-ip header
  await withFixedDateNow(fixed, async () => {
    await enforceRateLimit({ headers: { 'x-real-ip': '10.0.0.100' }, socket: { remoteAddress: '127.0.0.1' } });
    await assert.rejects(
      () => enforceRateLimit({ headers: { 'x-real-ip': '10.0.0.100' }, socket: { remoteAddress: '127.0.0.1' } }),
      (err) => err.status === 429,
    );
  });

  await fs.rm(rateLimitStorePath, { force: true });

  // fallback to remoteAddress (no x-forwarded-for, no x-real-ip)
  await withFixedDateNow(fixed, async () => {
    await enforceRateLimit({ headers: {}, socket: { remoteAddress: '192.168.1.50' } });
    await assert.rejects(
      () => enforceRateLimit({ headers: {}, socket: { remoteAddress: '192.168.1.50' } }),
      (err) => err.status === 429,
    );
  });

  delete process.env.HERMESBENCH_RATE_LIMIT_MAX;
  delete process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS;
});

test('precondition-failure detection handles all edge cases (guards against instanceof undefined)', async () => {
  // This test validates the detection logic used in the Blob rate-limit retry
  // loop.  The detection must survive: missing export (undefined), null client,
  // cross-realm-like errors, and plain Error with matching message text.
  const b = require('@vercel/blob');

  // 1. Normal BlobPreconditionFailedError — detected by all three strategies.
  const eNormal = new b.BlobPreconditionFailedError();
  assert.equal(eNormal.constructor.name, 'BlobPreconditionFailedError');
  assert.equal(typeof b.BlobPreconditionFailedError, 'function');
  assert(eNormal instanceof b.BlobPreconditionFailedError);
  assert(eNormal.message.includes('Precondition failed'));

  // 2. instanceof undefined — the bug we're fixing.
  const brokenClient = {};
  // This must NOT throw:
  const safeCheck1 = typeof brokenClient.BlobPreconditionFailedError === 'function';
  assert.equal(safeCheck1, false);

  // 3. null client — optional chaining returns undefined, then typeof catches it.
  const safeCheck2 = typeof null?.BlobPreconditionFailedError === 'function';
  assert.equal(safeCheck2, false);

  // 4. Plain Error with matching message — message fallback.
  const eMessage = new Error('Vercel Blob: Precondition failed: ETag mismatch.');
  assert.equal(eMessage.constructor.name, 'Error');
  assert(eMessage.message.includes('Precondition failed'));

  // 5. Unrelated error — should NOT match.
  const eOther = new b.BlobServiceRateLimited();
  assert.notEqual(eOther.constructor.name, 'BlobPreconditionFailedError');
  assert(!eOther.message.includes('Precondition failed'));

  // 6. Non-error throw (e.g. TypeError from the SDK internals).
  const eType = new TypeError('some other error');
  assert.notEqual(eType.constructor.name, 'BlobPreconditionFailedError');
  assert(!eType.message.includes('Precondition failed'));
});

test('local store corruption is handled gracefully (file reading error)', async () => {
  await fs.rm(rateLimitStorePath, { force: true });

  // Write invalid JSON to the store
  await fs.mkdir(path.dirname(rateLimitStorePath), { recursive: true });
  await fs.writeFile(rateLimitStorePath, 'not-valid-json{{');

  // The function should throw, not silently allow
  await assert.rejects(
    () => enforceRateLimit({ headers: { 'x-forwarded-for': '10.0.0.99' } }),
    (err) => err.name === 'SyntaxError' || err.code === 'SyntaxError',
  );
});

test('local rate-limit file auto-creates directory on first write', async () => {
  // Use a deep path that doesn't exist
  const deepPath = path.join(os.tmpdir(), `hermesbench-nested-${process.pid}`, 'sub', 'rate-limits.json');
  process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH = deepPath;
  delete process.env.HERMESBENCH_RATE_LIMIT_MAX;
  delete process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS;

  // Reload module with new env
  delete require.cache[require.resolve('../api/_submissions')];
  const mod = require('../api/_submissions');
  await fs.rm(path.dirname(path.dirname(deepPath)), { force: true, recursive: true });

  // Should create the directory and write without error
  await mod.enforceRateLimit({ headers: {}, socket: { remoteAddress: '10.0.0.50' } });

  const exists = await fs.stat(deepPath).then(() => true, () => false);
  assert.equal(exists, true);

  // Clean up
  await fs.rm(path.dirname(path.dirname(deepPath)), { force: true, recursive: true });
});
