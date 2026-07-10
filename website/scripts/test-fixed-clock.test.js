const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');
const test = require('node:test');

const { withFixedDateNow } = require('./test-fixed-clock');

const rateLimitStorePath = path.join(os.tmpdir(), `hermesbench-rate-clock-test-${process.pid}.json`);
process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH = rateLimitStorePath;
process.env.HERMESBENCH_RATE_LIMIT_MAX = '1';
process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS = '60';
delete process.env.BLOB_READ_WRITE_TOKEN;
const { enforceRateLimit } = require('../api/_submissions');

test('withFixedDateNow pins rate-limit assertions to one fixed minute bucket and restores Date.now', async () => {
  const originalDateNow = Date.now;
  const nearMinuteEnd = 1_800_059_998_999;
  const observed = [];

  await withFixedDateNow(nearMinuteEnd, async () => {
    observed.push(Date.now());
    await Promise.resolve();
    observed.push(Date.now());
  });

  assert.deepEqual(observed, [nearMinuteEnd, nearMinuteEnd]);
  assert.equal(Date.now, originalDateNow);
  assert.equal(Math.floor(observed[0] / 60_000), Math.floor(observed[1] / 60_000));
});

test('withFixedDateNow restores Date.now when a rate-limit assertion fails', async () => {
  const originalDateNow = Date.now;

  await assert.rejects(
    withFixedDateNow(1_800_059_998_999, async () => {
      throw new Error('expected smoke assertion failure');
    }),
    /expected smoke assertion failure/,
  );

  assert.equal(Date.now, originalDateNow);
});

test('fixed clock keeps two same-IP limiter requests in an artificial minute-end bucket', async () => {
  await fs.rm(rateLimitStorePath, { force: true });
  const request = { headers: { 'x-forwarded-for': '203.0.113.9' } };

  await withFixedDateNow(1_800_059_998_999, async () => {
    await enforceRateLimit(request);
    await assert.rejects(enforceRateLimit(request), (error) => error.status === 429);
  });
});
