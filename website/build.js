const fs = require('fs');
const path = require('path');

function cp(src, dst) {
  const st = fs.statSync(src);
  if (st.isDirectory()) {
    fs.mkdirSync(dst, { recursive: true });
    for (const f of fs.readdirSync(src)) cp(path.join(src, f), path.join(dst, f));
  } else {
    fs.mkdirSync(path.dirname(dst), { recursive: true });
    fs.copyFileSync(src, dst);
  }
}

function fail(file, msg) { throw new Error(`${file}: ${msg}`); }
function isObj(x) { return x && typeof x === 'object' && !Array.isArray(x); }
function num01(x) { return typeof x === 'number' && Number.isFinite(x) && x >= 0 && x <= 1; }
function maybeNum(x) { return x == null || (typeof x === 'number' && Number.isFinite(x)); }
function requireString(obj, key, file, where) { if (typeof obj[key] !== 'string' || !obj[key]) fail(file, `${where}.${key} must be a non-empty string`); }
function requireProvenance(obj, file, where, expected = null) {
  if (!isObj(obj)) fail(file, `${where} must be an object`);
  requireString(obj, 'data_status', file, where);
  requireString(obj, 'display_notice', file, where);
  if (typeof obj.capability_evidence !== 'boolean') fail(file, `${where}.capability_evidence must be a boolean`);
  if (expected && ['data_status', 'display_notice'].some((key) => obj[key] !== expected[key])) {
    fail(file, `${where} provenance must match the top-level payload`);
  }
  if (obj.evidence_class != null && !['historical_mock', 'official_evidence', 'unofficial_submission'].includes(obj.evidence_class)) {
    fail(file, `${where}.evidence_class is not recognized`);
  }
  if (obj.capability_evidence === true && obj.evidence_class === 'historical_mock') {
    fail(file, `${where} capability data cannot contain historical_mock evidence`);
  }
}
function isOfficialArchiveSource(source) {
  // Ported from scripts/archive_paths.py — pure JS, no Python needed at build time.
  if (typeof source !== 'string') return false;
  if (/%|\?|#|\\\\/.test(source)) return false;
  const parts = source.split('/');
  if (parts.length < 3) return false;
  if (parts[0] !== 'official-runs') return false;
  const SAFE_SEGMENT = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;
  return parts.slice(1).every((part) => part !== '' && part !== '.' && part !== '..' && SAFE_SEGMENT.test(part));
}
function rejectHistoricalMockCapabilityFields(value, file, where = 'root', historical = false) {
  if (Array.isArray(value)) return value.forEach((item, index) => rejectHistoricalMockCapabilityFields(item, file, `${where}[${index}]`, historical));
  if (!isObj(value)) return;
  const isHistorical = historical || value.evidence_class === 'historical_mock';
  for (const [key, item] of Object.entries(value)) {
    if (isHistorical && ['capability_pass', 'passed', 'passed_raw', 'passed_effective', 'status'].includes(key)) {
      fail(file, `${where}.${key} is forbidden in historical_mock public data`);
    }
    rejectHistoricalMockCapabilityFields(item, file, `${where}.${key}`, isHistorical);
  }
}
function rejectLocalSources(value, file, where = 'root') {
  if (Array.isArray(value)) return value.forEach((item, index) => rejectLocalSources(item, file, `${where}[${index}]`));
  if (!isObj(value)) return;
  for (const [key, item] of Object.entries(value)) {
    if (key === 'source' && typeof item === 'string' && (/^(?:\/|~|file:)/.test(item) || /^[A-Za-z]:[\\/]/.test(item))) {
      fail(file, `${where}.source must not expose an absolute or local path`);
    }
    if (key === 'source' && typeof item === 'string' && !isOfficialArchiveSource(item)) {
      fail(file, `${where}.source must be a normalized official-runs/<run>/... archive path or absent`);
    }
    rejectLocalSources(item, file, `${where}.${key}`);
  }
}
function requireScoreEntry(e, file, where, provenance) {
  if (!isObj(e)) fail(file, `${where} must be an object`);
  requireProvenance(e, file, where, provenance);
  requireString(e, 'evidence_class', file, where);
  for (const k of ['run_id', 'agent', 'suite']) requireString(e, k, file, where);
  const score = e.score_percentage ?? e.overall_score;
  if (e.evidence_class !== 'historical_mock' && !num01(score)) fail(file, `${where}.score_percentage/overall_score must be a 0..1 number`);
  for (const k of ['pass_at_1', 'false_done_rate', 'timeout_rate', 'raw_overall_score']) if (e[k] != null && !num01(e[k])) fail(file, `${where}.${k} must be a 0..1 number when present`);
  for (const k of ['task_count', 'total_score', 'max_score', 'total_execution_time_seconds', 'total_tokens', 'tool_call_count', 'total_cost_usd']) if (!maybeNum(e[k])) fail(file, `${where}.${k} must be numeric or null when present`);
  if (e.category_scores != null && !isObj(e.category_scores)) fail(file, `${where}.category_scores must be an object when present`);
  if (e.raw_category_scores != null && !isObj(e.raw_category_scores)) fail(file, `${where}.raw_category_scores must be an object when present`);
  const capability = e.evidence_class === 'official_evidence';
  if (e.capability_evidence !== capability) fail(file, `${where}.capability_evidence must match evidence_class`);
  if (capability && !isOfficialArchiveSource(e.source)) fail(file, `${where} official capability evidence requires an official-runs archive source`);
}
function validateLeaderboard(file, data) {
  if (!isObj(data)) fail(file, 'top-level JSON must be an object');
  requireProvenance(data, file, 'leaderboard');
  const arrays = ['entries', 'official', 'unofficial'].filter(k => Array.isArray(data[k]));
  if (!arrays.length) fail(file, 'must contain entries, official, or unofficial array');
  for (const key of arrays) data[key].forEach((e, i) => requireScoreEntry(e, file, `${key}[${i}]`, data));
  if (data.model_summaries != null && !Array.isArray(data.model_summaries)) fail(file, 'model_summaries must be an array');
}
function validateResult(file, data) {
  requireScoreEntry(data, file, 'result');
  if (data.schema_version !== 'hermesbench.score.v1') fail(file, 'schema_version must be hermesbench.score.v1');
  if (data.tasks != null) {
    if (!Array.isArray(data.tasks)) fail(file, 'tasks must be an array');
    data.tasks.forEach((t, i) => {
      if (!isObj(t)) fail(file, `tasks[${i}] must be an object`);
      requireString(t, 'task_id', file, `tasks[${i}]`);
      if (data.evidence_class === 'historical_mock') {
        if (typeof t.plumbing_audit !== 'string') fail(file, `tasks[${i}].plumbing_audit must describe the neutral fixture record`);
      } else {
        if (!num01(t.score)) fail(file, `tasks[${i}].score must be a 0..1 number`);
        if (typeof t.status !== 'string') fail(file, `tasks[${i}].status must be a string`);
      }
    });
  }
}
function walkJson(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const file = path.join(dir, entry.name);
    return entry.isDirectory() ? walkJson(file) : entry.name.endsWith('.json') ? [file] : [];
  });
}
function readJson(file) {
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  rejectLocalSources(data, file);
  rejectHistoricalMockCapabilityFields(data, file);
  if (path.basename(file) === 'leaderboard.json' || path.basename(file) === 'demo-leaderboard.json') validateLeaderboard(file, data);
  else validateResult(file, data);
  return data;
}

for (const file of walkJson('data')) readJson(file);
fs.rmSync('dist', { recursive: true, force: true });
fs.mkdirSync('dist', { recursive: true });
for (const f of ['index.html', 'app.js', 'data']) cp(f, path.join('dist', f));
console.log('website built; all public JSON provenance and paths validated');

module.exports = { isOfficialArchiveSource };
