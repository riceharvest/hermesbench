const crypto = require('node:crypto');
const fs = require('node:fs/promises');
const path = require('node:path');

const API_SCHEMA_VERSION = 'hermesbench.api.v0-dev';
const SUBMISSION_PREFIX = 'submissions/';
const COMMUNITY_SUBMISSION_PREFIX = 'community-submissions/';
const RATE_LIMIT_PREFIX = 'ratelimits/';
const LOCAL_STORE_PATH = process.env.HERMESBENCH_STORE_PATH || path.join(process.cwd(), '.tmp', 'submissions.jsonl');
const LOCAL_COMMUNITY_STORE_PATH = process.env.HERMESBENCH_COMMUNITY_STORE_PATH || path.join(process.cwd(), '.tmp', 'community-submissions.jsonl');
const LOCAL_RATE_LIMIT_STORE_PATH = process.env.HERMESBENCH_RATE_LIMIT_STORE_PATH || path.join(process.cwd(), '.tmp', 'rate-limits.json');
const SENSITIVE_LOG_KEYS = new Set(['logs', 'messages', 'transcript', 'stdout', 'stderr']);

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

function sendJson(res, status, body, extraHeaders = {}) {
  res.statusCode = status;
  for (const [key, value] of Object.entries({
    'content-type': 'application/json; charset=utf-8',
    'x-hermesbench-api-schema': API_SCHEMA_VERSION,
    ...corsHeaders(),
    ...extraHeaders,
  })) {
    res.setHeader(key, value);
  }
  res.end(JSON.stringify(body));
}

function corsHeaders() {
  const allowed = (process.env.HERMESBENCH_CORS_ORIGINS || 'https://hermesbench.site,http://localhost:4173,http://localhost:4177')
    .split(',')
    .map((origin) => origin.trim())
    .filter(Boolean);
  return {
    'access-control-allow-origin': allowed[0] || 'https://hermesbench.site',
    'access-control-allow-methods': 'GET,POST,OPTIONS',
    'access-control-allow-headers': 'content-type,x-hermesbench-submission-token,authorization',
  };
}

async function readBody(req) {
  if (req.body && typeof req.body === 'object') return req.body;
  if (typeof req.body === 'string') return JSON.parse(req.body || '{}');
  const chunks = [];
  for await (const chunk of req) chunks.push(Buffer.from(chunk));
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

function tokenFromRequest(req, payload, result) {
  const headerToken = req?.headers?.['x-hermesbench-submission-token'];
  const auth = req?.headers?.authorization || req?.headers?.Authorization;
  if (typeof headerToken === 'string' && headerToken) return headerToken;
  if (typeof auth === 'string' && auth.toLowerCase().startsWith('bearer ')) return auth.slice(7).trim();
  return payload?.submission_token || result?.submission_token;
}

function timingSafeEqual(a, b) {
  const left = Buffer.from(String(a || ''), 'utf8');
  const right = Buffer.from(String(b || ''), 'utf8');
  return left.length === right.length && crypto.timingSafeEqual(left, right);
}

function rejectReservedOfficial(payload, result) {
  if (payload.classification === 'official' || result.metadata?.official === true) {
    throw new Error('official flag is maintainer-reserved');
  }
}

function validateSubmission(payload, req = null) {
  const result = resultFromPayload(payload);
  validateResultShape(result);
  const expectedToken = process.env.HERMESBENCH_SUBMISSION_TOKEN;
  if (!expectedToken && process.env.VERCEL_ENV === 'production') {
    throw new ApiError(503, 'submission token is not configured');
  }
  const token = tokenFromRequest(req, payload, result);
  if (expectedToken && !timingSafeEqual(token, expectedToken)) {
    throw new ApiError(401, 'missing or invalid submission token');
  }
  rejectReservedOfficial(payload, result);
  return result;
}

function validateCommunitySubmission(payload) {
  const result = resultFromPayload(payload);
  validateResultShape(result);
  rejectReservedOfficial(payload, result);
  return result;
}

function sanitizeResult(result) {
  const clean = JSON.parse(JSON.stringify(result));
  delete clean.submission_token;
  for (const task of clean.results || []) {
    for (const key of Object.keys(task)) {
      if (SENSITIVE_LOG_KEYS.has(key.toLowerCase())) delete task[key];
    }
  }
  clean.metadata = { ...(clean.metadata || {}), sanitized: true };
  return clean;
}

function scorePayload(payload) {
  const rows = payload.results || [];
  const n = rows.length || 1;
  const overall = rows.reduce((sum, row) => sum + Number(row.score || 0), 0) / n;
  return {
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
}

function blobEnabled() {
  return Boolean(process.env.BLOB_READ_WRITE_TOKEN && blobClient?.put && blobClient?.list);
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

async function readBlobRateBucket(pathname) {
  if (!blobEnabled() || !blobClient?.get) return null;
  const found = await blobClient.get(pathname, { access: 'public' });
  if (!found?.stream) return null;
  return JSON.parse(await new Response(found.stream).text());
}

async function writeBlobRateBucket(pathname, bucket) {
  await blobClient.put(pathname, JSON.stringify(bucket), {
    access: 'public',
    addRandomSuffix: false,
    allowOverwrite: true,
    contentType: 'application/json',
  });
}

async function enforceRateLimit(req) {
  const { max, windowSeconds } = rateLimitConfig();
  if (max <= 0 || windowSeconds <= 0) return;
  const now = Date.now();
  const windowMs = windowSeconds * 1000;
  const windowStart = Math.floor(now / windowMs) * windowMs;
  const resetAt = Math.ceil((windowStart + windowMs) / 1000);
  const key = rateLimitKey(req, windowStart);
  const retryAfter = Math.max(1, resetAt - Math.ceil(now / 1000));

  if (blobEnabled() && blobClient?.get) {
    const pathname = `${RATE_LIMIT_PREFIX}${key}.json`;
    const bucket = (await readBlobRateBucket(pathname)) || { count: 0, reset_at: resetAt };
    bucket.count += 1;
    bucket.reset_at = resetAt;
    if (bucket.count > max) {
      throw new ApiError(429, 'rate limit exceeded', { 'retry-after': String(retryAfter) });
    }
    await writeBlobRateBucket(pathname, bucket);
    return;
  }

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

async function persistToStore(result, { prefix, localPath, storeName }) {
  if (blobEnabled()) {
    const pathname = submissionPath(result, prefix);
    await blobClient.put(pathname, JSON.stringify(result, null, 2), {
      access: 'public',
      addRandomSuffix: false,
      allowOverwrite: true,
      contentType: 'application/json',
    });
    return { store: 'vercel-blob', path: pathname };
  }
  await fs.mkdir(path.dirname(localPath), { recursive: true });
  await fs.appendFile(localPath, `${JSON.stringify(result)}\n`);
  return { store: storeName, path: localPath };
}

async function readStore({ prefix, localPath }) {
  if (blobEnabled()) {
    const listed = await blobClient.list({ prefix, limit: 1000 });
    const rows = [];
    for (const blob of listed.blobs || []) {
      try {
        const response = await fetch(blob.url);
        if (response.ok) rows.push(await response.json());
      } catch (_) {
        // Ignore a single malformed/unreachable blob; do not break leaderboard reads.
      }
    }
    return rows;
  }
  try {
    const text = await fs.readFile(localPath, 'utf8');
    return text.split('\n').filter(Boolean).map((line) => JSON.parse(line));
  } catch (error) {
    if (error.code === 'ENOENT') return [];
    throw error;
  }
}

async function persistSubmission(result) {
  return persistToStore(result, {
    prefix: SUBMISSION_PREFIX,
    localPath: LOCAL_STORE_PATH,
    storeName: 'local-jsonl',
  });
}

async function persistCommunitySubmission(result) {
  const communityResult = JSON.parse(JSON.stringify(result));
  communityResult.metadata = {
    ...(communityResult.metadata || {}),
    official: false,
    classification: 'community',
  };
  return persistToStore(communityResult, {
    prefix: COMMUNITY_SUBMISSION_PREFIX,
    localPath: LOCAL_COMMUNITY_STORE_PATH,
    storeName: 'community-jsonl',
  });
}

async function readSubmissions() {
  return readStore({ prefix: SUBMISSION_PREFIX, localPath: LOCAL_STORE_PATH });
}

async function readCommunitySubmissions() {
  return readStore({ prefix: COMMUNITY_SUBMISSION_PREFIX, localPath: LOCAL_COMMUNITY_STORE_PATH });
}

module.exports = {
  API_SCHEMA_VERSION,
  readBody,
  sendJson,
  validateSubmission,
  validateCommunitySubmission,
  sanitizeResult,
  enforceRateLimit,
  persistSubmission,
  persistCommunitySubmission,
  readSubmissions,
  readCommunitySubmissions,
  scorePayload,
  blobEnabled,
};
