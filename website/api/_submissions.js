const fs = require('node:fs/promises');
const path = require('node:path');

const API_SCHEMA_VERSION = 'hermesbench.api.v0-dev';
const SUBMISSION_PREFIX = 'submissions/';
const LOCAL_STORE_PATH = process.env.HERMESBENCH_STORE_PATH || path.join(process.cwd(), '.tmp', 'submissions.jsonl');
const SENSITIVE_LOG_KEYS = new Set(['logs', 'messages', 'transcript', 'stdout', 'stderr']);

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
    'access-control-allow-headers': 'content-type',
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

function validateSubmission(payload) {
  const result = resultFromPayload(payload);
  validateResultShape(result);
  const expectedToken = process.env.HERMESBENCH_SUBMISSION_TOKEN;
  const token = payload.submission_token || result.submission_token;
  if (expectedToken && token !== expectedToken) throw new Error('missing or invalid submission_token');
  if (payload.classification === 'official' || result.metadata?.official === true) {
    throw new Error('official flag is maintainer-reserved');
  }
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

function submissionPath(result) {
  const safeRun = String(result.run_id).replace(/[^a-zA-Z0-9_.-]+/g, '-').slice(0, 96) || 'unknown';
  return `${SUBMISSION_PREFIX}${safeRun}.json`;
}

async function persistSubmission(result) {
  if (blobEnabled()) {
    const pathname = submissionPath(result);
    await blobClient.put(pathname, JSON.stringify(result, null, 2), {
      access: 'public',
      addRandomSuffix: false,
      allowOverwrite: true,
      contentType: 'application/json',
    });
    return { store: 'vercel-blob', path: pathname };
  }
  await fs.mkdir(path.dirname(LOCAL_STORE_PATH), { recursive: true });
  await fs.appendFile(LOCAL_STORE_PATH, `${JSON.stringify(result)}\n`);
  return { store: 'local-jsonl', path: LOCAL_STORE_PATH };
}

async function readSubmissions() {
  if (blobEnabled()) {
    const listed = await blobClient.list({ prefix: SUBMISSION_PREFIX, limit: 1000 });
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
  sanitizeResult,
  persistSubmission,
  readSubmissions,
  scorePayload,
  blobEnabled,
};
