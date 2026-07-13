const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');

const API_SCHEMA_VERSION = 'hermesbench.api.v0-dev';
const SUBMISSION_PREFIX = 'submissions/';
const RATE_LIMIT_PREFIX = 'ratelimits/';
const LOCAL_STORE_PATH = process.env.HERMESBENCH_STORE_PATH || path.join(process.cwd(), '.tmp', 'submissions.jsonl');
const LOCAL_RATE_LIMIT_STORE_PATH = process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH || path.join(process.cwd(), '.tmp', 'rate-limits.json');
const SENSITIVE_LOG_KEYS = new Set(['logs', 'messages', 'transcript', 'stdout', 'stderr']);
const SUBMISSION_BLOB_ACCESS = process.env.HERMESBENCH_SUBMISSION_BLOB_ACCESS || 'public'; // 'public' or 'private'

// --- Security-hardening constants (all configurable via env) ---
const MAX_BODY_BYTES = Number.parseInt(process.env.HERMESBENCH_MAX_BODY_BYTES || (1024 * 1024).toString(), 10); // 1 MiB default
const MAX_RESULT_FIELDS_BYTES = Number.parseInt(process.env.HERMESBENCH_MAX_RESULT_FIELDS_BYTES || (512 * 1024).toString(), 10); // 512 KiB
const MAX_TASKS = Number.parseInt(process.env.HERMESBENCH_MAX_TASKS || '200', 10);
const MAX_METADATA_KEYS = Number.parseInt(process.env.HERMESBENCH_MAX_METADATA_KEYS || '20', 10);

// Fields allowed in public leaderboard responses (explicit allowlist).
const PUBLIC_SCORE_FIELDS = new Set(['run_id', 'agent', 'provider', 'model', 'suite', 'overall_score', 'pass_at_1', 'task_count', 'official', 'submitted_at']);

// Public intake is paused by default. Re-enable deliberately with an explicit
// deployment environment variable after a reviewed change.
function submissionsEnabled() {
  return process.env.HERMESBENCH_SUBMISSIONS_ENABLED === 'true';
}

class ApiError extends Error {
  constructor(status, message, headers = {}) {
    super(message);
    this.status = status;
    this.headers = headers;
  }
}

let blobClient = null;
try {
  blobClient = require('@vercel/blob');
} catch (_) {
  blobClient = null;
}

function sendJson(res, status, body, extraHeaders = {}, req = null) {
  res.statusCode = status;
  for (const [key, value] of Object.entries({
    'content-type': 'application/json; charset=utf-8',
    'x-hermesbench-api-schema': API_SCHEMA_VERSION,
    ...corsHeaders(req),
    ...extraHeaders,
  })) {
    res.setHeader(key, value);
  }
  res.end(JSON.stringify(body));
}

/**
 * Build CORS headers. Origin-aware: returns the request's Origin header value
 * only if it appears in the allowlist; falls back to allowed[0] when no Origin
 * is present.  Emits Vary: Origin so intermediaries don't cache the same response
 * for different origins.  Never emits a wildcard.
 */
function corsHeaders(req) {
  const allowed = (process.env.HERMESBENCH_CORS_ORIGINS || 'https://www.benchcut.info,http://localhost:4173,http://localhost:4177')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
  const defaultOrigin = allowed[0] || 'https://www.benchcut.info';
  const reqOrigin = req?.headers?.origin || req?.headers?.Origin || null;
  const matchedOrigin = reqOrigin && allowed.includes(reqOrigin) ? reqOrigin : null;
  return {
    'access-control-allow-origin': matchedOrigin || defaultOrigin,
    'vary': 'Origin',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type,x-hermesbench-submission-token,authorization',
  };
}

async function readBody(req) {
  if (req.body && typeof req.body === 'object') {
    const bodyBytes = Buffer.byteLength(JSON.stringify(req.body), 'utf8');
    if (bodyBytes > MAX_BODY_BYTES) {
      throw new ApiError(413, `request body exceeds ${MAX_BODY_BYTES} byte limit`);
    }
    return req.body;
  }
  if (typeof req.body === 'string') {
    const bodyBytes = Buffer.byteLength(req.body, 'utf8');
    if (bodyBytes > MAX_BODY_BYTES) {
      throw new ApiError(413, `request body exceeds ${MAX_BODY_BYTES} byte limit`);
    }
    return JSON.parse(req.body || '{}');
  }
  const chunks = [];
  let totalBytes = 0;
  for await (const chunk of req) {
    const buf = Buffer.from(chunk);
    totalBytes += buf.length;
    if (totalBytes > MAX_BODY_BYTES) {
      throw new ApiError(413, `request body exceeds ${MAX_BODY_BYTES} byte limit`);
    }
    chunks.push(buf);
  }
  const raw = Buffer.concat(chunks).toString('utf8');
  return raw ? JSON.parse(raw) : {};
}

function resultFromPayload(payload) {
  if (payload && payload.schema_version === 'hermesbench.submission.v1') {
    if (!payload.result || typeof payload.result !== 'object') throw new Error('missing result field in submission payload');
    return payload.result;
  }
  return payload;
}

function validateResultShape(result) {
  if (!result || typeof result !== 'object') throw new Error('missing result payload');
  if (result.schema_version !== 'hermesbench.result.v1') throw new Error('missing or invalid schema_version');
  for (const field of ['run_id', 'agent', 'suite']) {
    if (typeof result[field] !== 'string' || !result[field]) throw new Error(`missing result field: ${field}`);
  }
  if (!Array.isArray(result.results)) throw new Error('missing result field: results');
}

function tokenFromRequest(req) {
  const headerToken = req?.headers?.['x-hermesbench-submission-token'];
  if (typeof headerToken === 'string' && headerToken) return headerToken;
  const auth = req?.headers?.authorization || req?.headers?.Authorization;
  if (typeof auth === 'string' && auth.toLowerCase().startsWith('bearer ')) return auth.slice(7).trim();
  return null;
}

function timingSafeEqual(a, b) {
  const left = Buffer.from(String(a || ''), 'utf8');
  const right = Buffer.from(String(b || ''), 'utf8');
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

function validateSubmission(payload, req = null) {
  const result = resultFromPayload(payload);
  validateResultShape(result);

  // Reject official-flagged submissions — only maintainers use the offline archive-official flow.
  if (
    (typeof payload.classification === 'string' && payload.classification.toLowerCase() === 'official') ||
    (result.metadata && result.metadata.official === true)
  ) {
    throw new ApiError(400, 'official flag is maintainer-reserved');
  }

  // Reject mock agent submissions.
  if (result.agent === 'mock') {
    throw new ApiError(400, 'mock agent submissions are not accepted');
  }

  // Enforce reasonable bounds on payload fields.
  if (Array.isArray(result.results) && result.results.length > MAX_TASKS) {
    throw new ApiError(413, `task count ${result.results.length} exceeds maximum ${MAX_TASKS}`);
  }
  if (result.metadata && typeof result.metadata === 'object') {
    const metaKeys = Object.keys(result.metadata);
    if (metaKeys.length > MAX_METADATA_KEYS) {
      throw new ApiError(413, `metadata key count ${metaKeys.length} exceeds maximum ${MAX_METADATA_KEYS}`);
    }
  }
  const serializedBytes = Buffer.byteLength(JSON.stringify(result), 'utf8');
  if (serializedBytes > MAX_RESULT_FIELDS_BYTES) {
    throw new ApiError(413, `result payload ${serializedBytes} bytes exceeds ${MAX_RESULT_FIELDS_BYTES} byte limit`);
  }

  const expectedToken = process.env.HERMESBENCH_SUBMISSION_TOKEN;
  if (!expectedToken && process.env.VERCEL_ENV === 'production') {
    throw new ApiError(503, 'submission token is not configured');
  }
  const token = tokenFromRequest(req);
  if (expectedToken && !timingSafeEqual(token, expectedToken)) {
    throw new ApiError(401, 'missing or invalid submission token');
  }
  return result;
}

// Fields allowed in sanitized public-safe result payloads (metadata + task-level).
// Only fields listed here are retained — everything else is stripped.
const PUBLIC_METADATA_KEYS = new Set([
  'sanitized', 'official',
  // Run-ledger metadata (non-secret identity, runtime, provenance, hardware)
  'provider', 'model', 'reasoning_effort', 'quantization', 'backend',
  'profile', 'benchmark_version', 'jobs', 'run_wall_time_seconds',
  'engine_version', 'hermes_version', 'git_commit', 'command',
  'config_summary',
  'private_pack_id',
  'os_platform', 'python_version', 'cpu_info', 'gpu_info',
  'metadata_available',
  // Legacy fields kept for backward compatibility
  'agent_version', 'runner', 'environment', 'ci_run', 'suite',
]);
const PUBLIC_TASK_KEYS = new Set([
  'task_id', 'category', 'status', 'score', 'passed',
  'wall_time_seconds', 'tool_calls', 'token_usage',
  'checks', 'timeout', 'false_done', 'plumbing_audit', 'source',
]);

function sanitizeResult(result) {
  const clean = JSON.parse(JSON.stringify(result));
  delete clean.submission_token;
  delete clean.run_id_hash;

  // Strip any sensitive log/transcript keys from the top level.
  for (const key of Object.keys(clean)) {
    if (SENSITIVE_LOG_KEYS.has(key.toLowerCase())) delete clean[key];
  }

  // Explicit allowlist for metadata (public-safe fields only).
  if (clean.metadata && typeof clean.metadata === 'object') {
    const safeMeta = {};
    for (const key of Object.keys(clean.metadata)) {
      if (PUBLIC_METADATA_KEYS.has(key)) safeMeta[key] = clean.metadata[key];
    }
    safeMeta.sanitized = true;
    clean.metadata = safeMeta;
  } else {
    clean.metadata = { sanitized: true };
  }

  // Explicit allowlist for each task-level result entry.
  if (Array.isArray(clean.results)) {
    clean.results = clean.results.map((task) => {
      const safe = {};
      for (const key of PUBLIC_TASK_KEYS) {
        if (Object.prototype.hasOwnProperty.call(task, key)) safe[key] = task[key];
      }
      return safe;
    });
  }
  return clean;
}

function scorePayload(payload) {
  const rows = payload.results || [];
  const n = rows.length || 1;
  const overall = rows.reduce((sum, row) => sum + Number(row.score || 0), 0) / n;
  const entry = {
    run_id: payload.run_id,
    agent: payload.agent,
    provider: payload.provider || null,
    model: payload.model || null,
    suite: payload.suite,
    overall_score: overall,
    pass_at_1: rows.filter((row) => row.passed).length / n,
    task_count: rows.length,
    official: Boolean(payload.metadata?.official),
    submitted_at: payload.submitted_at || payload.completed_at || null,
  };
  // Explicit public field allowlist — strip anything not in PUBLIC_SCORE_FIELDS.
  for (const key of Object.keys(entry)) {
    if (!PUBLIC_SCORE_FIELDS.has(key)) delete entry[key];
  }
  return entry;
}

function blobEnabled() {
  return Boolean(
    process.env.BLOB_READ_WRITE_TOKEN &&
    blobClient?.put &&
    blobClient?.head &&
    blobClient?.get &&
    blobClient?.list
  );
}

/**
 * Compute a content-hash-based filename for a submission blob.
 *
 * The path is deterministic given the same run_id + token, but only the
 * submitter who knows the token can predict it, making the path de facto
 * unguessable to an external observer.  This prevents enumeration and
 * ensures identical re-submissions hit the same path (idempotent merge).
 */
function submissionBlobPath(result) {
  const safeRun = String(result.run_id).replace(/[^a-zA-Z0-9_.-]+/g, '-').slice(0, 96) || 'unknown';
  const token = process.env.HERMESBENCH_SUBMISSION_TOKEN || '';
  const hash = crypto.createHash('sha256').update(safeRun + ':' + token).digest('hex').slice(0, 16);
  return `${SUBMISSION_PREFIX}${hash}-${safeRun}.json`;
}

function submissionPath(result, prefix = SUBMISSION_PREFIX) {
  const safeRun = String(result.run_id).replace(/[^a-zA-Z0-9_.-]+/g, '-').slice(0, 96) || 'unknown';
  return `${prefix}${safeRun}.json`;
}

function requestIp(req) {
  const forwarded = req?.headers?.['x-forwarded-for'];
  const firstForwarded = Array.isArray(forwarded) ? forwarded[0] : forwarded;
  const ip = String(firstForwarded || req?.headers?.['x-real-ip'] || req?.socket?.remoteAddress || 'unknown')
    .split(',')[0]
    .trim();
  return ip || 'unknown';
}

function rateLimitConfig() {
  const max = Number.parseInt(process.env.HERMESBENCH_RATE_LIMIT_MAX || '12', 10);
  const windowSeconds = Number.parseInt(process.env.HERMESBENCH_RATE_LIMIT_WINDOW_SECONDS || '600', 10);
  return {
    max: Number.isFinite(max) ? max : 12,
    windowSeconds: Number.isFinite(windowSeconds) ? windowSeconds : 600,
  };
}

function rateLimitKey(req, windowStart) {
  const hash = crypto.createHash('sha256').update(requestIp(req)).digest('hex').slice(0, 32);
  return `${hash}:${windowStart}`;
}

async function readLocalRateBuckets() {
  try {
    return JSON.parse(await fs.readFile(LOCAL_RATE_LIMIT_STORE_PATH, 'utf8'));
  } catch (error) {
    if (error.code === 'ENOENT') return {};
    throw error;
  }
}

async function writeLocalRateBuckets(buckets) {
  await fs.mkdir(path.dirname(LOCAL_RATE_LIMIT_STORE_PATH), { recursive: true });
  await fs.writeFile(LOCAL_RATE_LIMIT_STORE_PATH, JSON.stringify(buckets));
}

/**
 * Rate-limit bucket stored in Vercel Blob.
 *
 * Concurrency model: optimistic concurrency via ETag (ifMatch).
 * This is the safest mechanism Vercel Blob offers — it is NOT a distributed lock.
 * Under extreme concurrent contention (e.g. multiple rapid-fire requests from the
 * same IP within the same window), two reads may observe the same ETag, both
 * attempt conditional puts, and one succeeds while the other retries. The retry
 * loop (max 3 attempts) makes the race window vanishingly small but does NOT
 * guarantee strict linearizability across Vercel's global edge.
 *
 * If the Blob precondition check fails on every retry, the request is FAIL-CLOSED
 * (thrown as a 429) rather than silently allowing the request through. In
 * practice this is a safe conservative stance — the rate-limit check is
 * preferentially strict.
 *
 * The local-filesystem path (used outside Vercel) is single-process and
 * effectively atomic by nature of Node.js event loop serialization.
 */
const BLOB_RATE_LIMIT_RETRIES = 3;

async function enforceRateLimit(req) {
  const { max, windowSeconds } = rateLimitConfig();
  if (max <= 0 || windowSeconds <= 0) return;
  const now = Date.now();
  const windowMs = windowSeconds * 1000;
  const windowStart = Math.floor(now / windowMs) * windowMs;
  const resetAt = Math.ceil((windowStart + windowMs) / 1000);
  const key = rateLimitKey(req, windowStart);
  const retryAfter = Math.max(1, resetAt - Math.ceil(now / 1000));

  // --- Blob (Vercel) path: optimistic concurrency via ETag ---
  if (blobEnabled() && blobClient?.head && blobClient?.put) {
    const pathname = `${RATE_LIMIT_PREFIX}${key}.json`;

    for (let attempt = 0; attempt < BLOB_RATE_LIMIT_RETRIES; attempt++) {
      // Read current blob state and its ETag.
      // head() is safe for non-existent blobs (returns null).
      let current;
      try {
        current = await blobClient.head(pathname);
      } catch (_) {
        current = null;
      }

      let bucket;
      let etag = null;

      if (current) {
        etag = current.etag || null;
        // Fetch the actual content to get the count
        const found = await blobClient.get(pathname, { access: 'public' });
        if (found?.stream) {
          bucket = JSON.parse(await new Response(found.stream).text());
        } else {
          bucket = null;
        }
      }

      if (!bucket || !etag) {
        // First write — no existing blob. IfMatch cannot be used on first write.
        bucket = { count: 0, reset_at: resetAt };
      }

      bucket.count += 1;
      bucket.reset_at = resetAt;

      if (bucket.count > max) {
        throw new ApiError(429, 'rate limit exceeded', { 'retry-after': String(retryAfter) });
      }

      try {
        const putOpts = {
          access: 'public',
          addRandomSuffix: false,
          allowOverwrite: false,
          contentType: 'application/json',
        };
        if (etag) {
          putOpts.ifMatch = etag;
        }
        await blobClient.put(pathname, JSON.stringify(bucket), putOpts);
        return; // Success — written atomically.
      } catch (err) {
        // BlobPreconditionFailedError means another request wrote first.
        // Retry the full read-increment-write cycle.
        //
        // Detection strategy (defensive across API versions and runtimes):
        //   1. constructor.name check (works even when instanceof fails due
        //      to cross-realm / VM-context boundaries or monkey-patched exports)
        //   2. instanceof guard — only safe when blobClient.BlobPreconditionFailedError
        //      is a function (avoids TypeError on `instanceof undefined`)
        //   3. message-text fallback as a last resort
        const isPreconditionFailure =
          err?.constructor?.name === 'BlobPreconditionFailedError' ||
          (typeof blobClient?.BlobPreconditionFailedError === 'function' &&
            err instanceof blobClient.BlobPreconditionFailedError) ||
          (typeof err?.message === 'string' && err.message.includes('Precondition failed'));
        if (isPreconditionFailure && attempt < BLOB_RATE_LIMIT_RETRIES - 1) {
          continue;
        }
        // Any other error, or retries exhausted: fail-closed.
        throw new ApiError(429, 'rate limit conflict — try again', { 'retry-after': String(retryAfter) });
      }
    }
    // If we exhaust retries without success or return, fail closed.
    throw new ApiError(429, 'rate limit conflict — try again', { 'retry-after': String(retryAfter) });
  }

  // --- Local filesystem path (single-process, effectively atomic) ---
  const buckets = await readLocalRateBuckets();
  const freshBuckets = Object.fromEntries(Object.entries(buckets).filter(([, bucket]) => Number(bucket.reset_at || 0) > Math.ceil(now / 1000)));
  const bucket = freshBuckets[key] || { count: 0, reset_at: resetAt };
  bucket.count += 1;
  bucket.reset_at = resetAt;
  if (bucket.count > max) {
    throw new ApiError(429, 'rate limit exceeded', { 'retry-after': String(retryAfter) });
  }
  freshBuckets[key] = bucket;
  await writeLocalRateBuckets(freshBuckets);
}

/**
 * Persist a submission to Vercel Blob with fail-closed, idempotent semantics.
 *
 * Blob path is derived from `submissionBlobPath()` — deterministic for the
 * same run_id + token hash, but unguessable without the token.
 *
 * Duplicate handling (same run_id, same content):
 *   `run_id_hash` is stored inside the blob. On re-submission with identical
 *   content (same run_id, same result body), the read-then-write cycle will
 *   see the existing blob and compare `run_id_hash` + complete body. If the
 *   result is byte-for-byte identical, the submission is accepted (idempotent
 *   202).  If different, the submission is rejected with a deterministic 409
 *   conflict error.
 *
 * Production enforcement:
 *   - When `process.env.VERCEL === '1'` and Blob is NOT enabled, throws 503.
 *   - The local-filesystem path is retained for development/testing only and
 *     MUST NOT be used in a Vercel deployment.
 */
async function persistSubmission(result) {
  // In a Vercel runtime, fail closed if Blob is not configured.
  if (process.env.VERCEL === '1' && !blobEnabled()) {
    throw new ApiError(503, 'submission storage (Vercel Blob) is not configured');
  }

  if (blobEnabled()) {
    const pathname = submissionBlobPath(result);
    const runIdHash = crypto.createHash('sha256').update(String(result.run_id)).digest('hex');
    // Keep the internal identity hash in storage so duplicate checks are
    // deterministic; sanitizeResult removes it from every public response.
    const storedResult = { ...result, run_id_hash: runIdHash };
    const body = JSON.stringify(storedResult, null, 2);

    // Check if a blob already exists at this path (ETag-based conditional).
    let existing;
    try {
      existing = await blobClient.head(pathname);
    } catch (_) {
      existing = null;
    }

    if (existing) {
      // Blob exists — determine whether this is an identical re-submit or a conflict.
      let existingBody;
      try {
        const found = await blobClient.get(pathname, { access: SUBMISSION_BLOB_ACCESS });
        if (found?.stream) {
          existingBody = await new Response(found.stream).text();
        }
      } catch (_) {
        // Fall through — treat read failure as an error, not a conflict.
      }

      if (existingBody !== undefined) {
        // Compare by extracting the stored run_id_hash.
        let existingResult;
        try {
          existingResult = JSON.parse(existingBody);
        } catch (_) {
          existingResult = null;
        }
        const existingRunIdHash = existingResult?.run_id_hash || '';
        const isIdentical = existingRunIdHash === runIdHash && existingBody === body;

        if (isIdentical) {
          return { store: 'vercel-blob', path: pathname, conflict: false, duplicate: true };
        }

        // Conflicting content — reject with a deterministic response.
        throw new ApiError(409, `duplicate run_id '${result.run_id}' with conflicting content — submission rejected`);
      }

      // Could not read existing body (unexpected).  Fail closed rather than
      // silently overwriting or accepting without comparison.
      throw new ApiError(503, 'cannot verify submission uniqueness — storage read failed');
    }

    // First write — use allowOverwrite: false for safety, but with the
    // unguessable path this would only collide via the same submitter
    // sending a genuinely different payload for the same run_id.
    // Catch BlobPreconditionFailedError (race: concurrent request wrote first)
    // and re-read to check idempotency instead of crashing.
    try {
      await blobClient.put(pathname, body, {
        access: SUBMISSION_BLOB_ACCESS,
        addRandomSuffix: false,
        allowOverwrite: false,
        contentType: 'application/json',
      });
    } catch (err) {
      const isPreconditionFailure =
        err?.constructor?.name === 'BlobPreconditionFailedError' ||
        (typeof blobClient?.BlobPreconditionFailedError === 'function' &&
          err instanceof blobClient.BlobPreconditionFailedError) ||
        (typeof err?.message === 'string' && err.message.includes('Precondition failed'));
      if (isPreconditionFailure) {
        // Another request just wrote this blob.  Re-read to check identity.
        let found;
        try {
          found = await blobClient.get(pathname, { access: SUBMISSION_BLOB_ACCESS });
        } catch (_) {
          found = null;
        }
        if (found?.stream) {
          const existingBody = await new Response(found.stream).text();
          const isIdentical = existingBody === body;
          if (isIdentical) {
            return { store: 'vercel-blob', path: pathname, conflict: false, duplicate: true };
          }
        }
        // Conflicting or unreadable — reject, don't overwrite.
        throw new ApiError(409, `duplicate run_id '${result.run_id}' with conflicting content — submission rejected`);
      }
      // Non-precondition error: rethrow as a 503 fail-closed.
      throw new ApiError(503, `submission storage write failed: ${err.message}`);
    }

    return { store: 'vercel-blob', path: pathname, conflict: false };
  }

  // --- Local filesystem path (development/testing only) ---
  await fs.mkdir(path.dirname(LOCAL_STORE_PATH), { recursive: true });
  // For local store, check for existing run_id and handle duplicates.
  let existingLines = [];
  try {
    const text = await fs.readFile(LOCAL_STORE_PATH, 'utf8');
    existingLines = text.split('\n').filter(Boolean).map((line) => JSON.parse(line));
  } catch (error) {
    if (error.code !== 'ENOENT') throw error;
    existingLines = [];
  }

  const runId = result.run_id;
  const existingEntry = existingLines.find((e) => e.run_id === runId);
  if (existingEntry) {
    const existingStr = JSON.stringify(existingEntry);
    const newStr = JSON.stringify(result);
    if (existingStr === newStr) {
      return { store: 'local-jsonl', path: LOCAL_STORE_PATH, conflict: false, duplicate: true };
    }
    throw new ApiError(409, `duplicate run_id '${runId}' with conflicting content — submission rejected`);
  }

  await fs.appendFile(LOCAL_STORE_PATH, `${JSON.stringify(result)}\n`);
  return { store: 'local-jsonl', path: LOCAL_STORE_PATH, conflict: false };
}

async function readSubmissions() {
  if (blobEnabled()) {
    const listed = await blobClient.list({ prefix: SUBMISSION_PREFIX, limit: 1000 });
    const rows = [];
    for (const blob of listed.blobs || []) {
      try {
        const found = await blobClient.get(blob.url, { access: SUBMISSION_BLOB_ACCESS });
        if (found?.stream) {
          rows.push(JSON.parse(await new Response(found.stream).text()));
        }
      } catch (_) {
        // Ignore a single malformed/unreachable blob; do not break leaderboard reads.
      }
    }
    return rows;
  }
  try {
    const text = await fs.readFile(LOCAL_STORE_PATH, 'utf8');
    return text.split('\n').filter(Boolean).map((line) => JSON.parse(line));
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
}

module.exports = {
  API_SCHEMA_VERSION,
  readBody,
  sendJson,
  validateSubmission,
  tokenFromRequest,
  sanitizeResult,
  enforceRateLimit,
  persistSubmission,
  readSubmissions,
  scorePayload,
  blobEnabled,
  submissionBlobPath,
  submissionPath,
  submissionsEnabled,
};
