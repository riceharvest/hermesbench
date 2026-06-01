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
function requireScoreEntry(e, file, where) {
  if (!isObj(e)) fail(file, `${where} must be an object`);
  for (const k of ['run_id', 'agent', 'suite']) requireString(e, k, file, where);
  const score = e.score_percentage ?? e.overall_score;
  if (!num01(score)) fail(file, `${where}.score_percentage/overall_score must be a 0..1 number`);
  for (const k of ['pass_at_1', 'false_done_rate', 'timeout_rate', 'raw_overall_score']) if (e[k] != null && !num01(e[k])) fail(file, `${where}.${k} must be a 0..1 number when present`);
  for (const k of ['task_count', 'total_score', 'max_score', 'total_execution_time_seconds', 'total_tokens', 'tool_call_count', 'total_cost_usd']) if (!maybeNum(e[k])) fail(file, `${where}.${k} must be numeric or null when present`);
  if (e.category_scores != null && !isObj(e.category_scores)) fail(file, `${where}.category_scores must be an object when present`);
  if (e.raw_category_scores != null && !isObj(e.raw_category_scores)) fail(file, `${where}.raw_category_scores must be an object when present`);
}
function validateLeaderboard(file, data) {
  if (!isObj(data)) fail(file, 'top-level JSON must be an object');
  const arrays = ['entries', 'official', 'unofficial'].filter(k => Array.isArray(data[k]));
  if (!arrays.length) fail(file, 'must contain entries, official, or unofficial array');
  for (const key of arrays) data[key].forEach((e, i) => requireScoreEntry(e, file, `${key}[${i}]`));
  if (data.model_summaries != null) {
    if (!Array.isArray(data.model_summaries)) fail(file, 'model_summaries must be an array');
    data.model_summaries.forEach((s, i) => {
      if (!isObj(s)) fail(file, `model_summaries[${i}] must be an object`);
      if (!s.model && !s.model_key) fail(file, `model_summaries[${i}] must include model or model_key`);
      const score = s.average_score_percentage ?? s.best_score_percentage ?? s.score_percentage ?? s.overall_score;
      if (!num01(score)) fail(file, `model_summaries[${i}] must include a 0..1 score`);
    });
  }
}
function validateLatestResult(file, data) {
  requireScoreEntry(data, file, 'result');
  if (data.schema_version !== 'hermesbench.score.v1') fail(file, 'schema_version must be hermesbench.score.v1');
  if (data.tasks != null) {
    if (!Array.isArray(data.tasks)) fail(file, 'tasks must be an array');
    data.tasks.forEach((t, i) => {
      if (!isObj(t)) fail(file, `tasks[${i}] must be an object`);
      requireString(t, 'task_id', file, `tasks[${i}]`);
      if (!num01(t.score)) fail(file, `tasks[${i}].score must be a 0..1 number`);
      if (typeof t.status !== 'string') fail(file, `tasks[${i}].status must be a string`);
    });
  }
}
function readJson(file) {
  const data = JSON.parse(fs.readFileSync(file, 'utf8'));
  if (file.endsWith('leaderboard.json')) validateLeaderboard(file, data);
  if (file.endsWith('latest-result.json')) validateLatestResult(file, data);
  return data;
}

for (const f of ['data/leaderboard.json', 'data/latest-result.json']) readJson(f);
fs.rmSync('dist', { recursive: true, force: true });
fs.mkdirSync('dist', { recursive: true });
for (const f of ['index.html', 'app.js', 'data']) cp(f, path.join('dist', f));
console.log('website built; leaderboard/result JSON validated');
