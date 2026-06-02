async function loadJson(path) {
  const response = await fetch(path);
  if (!response.ok) throw new Error(`Could not load ${path}`);
  return response.json();
}

const escapeHtml = (value) => String(value ?? '').replace(/[&<>"]/g, (char) => ({
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
}[char]));

const fmt = {
  pct(value, digits = 0) {
    return value == null || Number.isNaN(Number(value)) ? 'n/a' : `${(Number(value) * 100).toFixed(digits)}%`;
  },
  num(value, digits = 0) {
    return value == null || Number.isNaN(Number(value))
      ? 'n/a'
      : Number(value).toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
  },
  compact(value) {
    return value == null || Number.isNaN(Number(value))
      ? 'n/a'
      : Number(value).toLocaleString(undefined, { notation: 'compact', maximumFractionDigits: 2 });
  },
  seconds(value) {
    if (value == null || Number.isNaN(Number(value))) return 'n/a';
    const n = Number(value);
    return `${n.toFixed(n < 10 ? 1 : 0)}s`;
  },
  money(value) {
    return value == null || Number.isNaN(Number(value)) ? 'n/a' : `$${Number(value).toFixed(4)}`;
  },
};
const DATA_BASE = 'data';
const defaultApiEndpoint = 'https://hermesbench.site/v1/results';

const routes = [
  ['/', 'Overview'],
  ['/leaderboard', 'Leaderboard'],
  ['/tasks', 'Tasks'],
  ['/methodology', 'Scoring'],
  ['/submit', 'Run it'],
];

const taskStats = {
  total: 80,
  publicDev: 55,
  longHorizon: 10,
  packs: [
    ['Short reliability', 'public-dev', '55', 'Fast local tasks for tool use, file reads, edits, test runs, and final-answer honesty.'],
    ['Long-horizon endurance', 'long-horizon-dev', '10', 'Multi-stage jobs where the agent must keep context, recover from friction, and prove the result.'],
    ['Anchor set', 'anchor', '5', 'Stable tasks retained over time so old and new runs can be compared without moving the goalposts.'],
    ['Fresh waves', 'fresh-rolling', '5', 'New public tasks that make memorization less useful and keep the benchmark alive.'],
    ['Private holdout', 'private-holdout', '5', 'Hidden official tasks for cleaner rankings when maintainers need a less gameable read.'],
  ],
  categories: [
    'read files', 'edit files', 'run tests', 'debug CI', 'inspect logs', 'analyze CSVs',
    'research docs', 'fix bugs', 'write artifacts', 'harden Docker', 'recover context',
    'catch false done', 'use browser', 'schedule jobs', 'respect privacy', 'summarize evidence',
  ],
};

const state = {
  leaderboard: null,
  latest: null,
  runCache: new Map(),
  filter: '',
  suite: '',
  sort: 'score',
  lastPath: '',
  command: {
    agent: 'hermes',
    provider: 'openai-codex',
    model: 'gpt-5.5',
    reasoning: 'low',
    suite: 'public-dev',
    task: '',
    jobs: 'auto',
    outputDir: 'results/hermes-openai-codex-gpt-5.5-public-dev-low',
    endpoint: defaultApiEndpoint,
  },
};

function sourceRows(leaderboard = state.leaderboard) {
  if (!leaderboard) return [];
  if ((leaderboard.official || []).length || (leaderboard.unofficial || []).length) {
    return [...(leaderboard.official || []), ...(leaderboard.unofficial || [])];
  }
  return [...(leaderboard.entries || [])];
}

function dedupe(rows) {
  const seen = new Set();
  return rows.filter((row) => {
    const key = row.run_id || row.best_submission_id || `${row.provider}/${row.model}/${row.suite}/${row.reasoning_effort}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function scoreOf(row) {
  return row.score_percentage ?? row.overall_score ?? row.average_score_percentage ?? row.best_score_percentage ?? 0;
}

function rawOf(row) {
  return row.raw_overall_score ?? row.raw_score_percentage ?? row.best_raw_score_percentage ?? scoreOf(row);
}

function reliabilityOf(row) {
  const explicit = row.reliability_score;
  if (explicit != null) return explicit;
  const falseDone = row.false_done_rate ?? row.average_false_done_rate ?? 0;
  const timeout = row.timeout_rate ?? row.average_timeout_rate ?? 0;
  return Math.max(0, 1 - (falseDone * .65 + timeout * .35));
}

function tokenEfficiencyOf(row) {
  const explicit = row.token_efficiency_score;
  if (explicit != null) return explicit;
  const tokens = row.total_tokens ?? row.average_total_tokens;
  return tokens && scoreOf(row) ? (scoreOf(row) / tokens) * 1_000_000 : null;
}

function valueOf(row) {
  if (row.value_score != null) return row.value_score;
  const cost = row.total_cost_usd ?? row.cost_usd;
  return cost && scoreOf(row) ? scoreOf(row) / cost : null;
}

function runIdOf(row) {
  return row.best_submission_id || row.run_id || '';
}

function modelLabel(row) {
  const model = [row.provider, row.model].filter(Boolean).join('/') || 'unknown model';
  return row.reasoning_effort ? `${model} / ${row.reasoning_effort}` : model;
}

function modelTitle(row) {
  const model = row.model || [row.provider, row.model].filter(Boolean).join('/') || 'unknown model';
  const spaced = String(model).replaceAll('/', ' / ');
  return row.reasoning_effort ? `${spaced} / ${row.reasoning_effort}` : spaced;
}

function providerLine(row) {
  return [row.provider, row.agent, row.suite].filter(Boolean).join(' / ') || 'benchmark run';
}

function statusLabel(row) {
  return row.official || row.classification === 'official' ? 'official' : 'sample';
}

function passedOf(row) {
  return row.best_passed_task_count ?? row.passed_task_count;
}

function failedOf(row) {
  return row.best_failed_task_count ?? row.failed_task_count;
}

function timeoutCountOf(row) {
  return row.best_timeout_count ?? row.timeout_count;
}

function falseDoneCountOf(row) {
  return row.best_false_done_count ?? row.false_done_count;
}

function taskCountOf(row) {
  return row.best_task_count ?? row.task_count;
}

function medianTimeOf(row) {
  return row.best_median_wall_time_seconds ?? row.median_wall_time_seconds;
}

function tokenCountOf(row) {
  return row.average_total_tokens ?? row.total_tokens ?? row.token_usage?.total_tokens;
}

function currentRows() {
  const query = state.filter.trim().toLowerCase();
  const rows = dedupe(sourceRows()).filter((row) => {
    const haystack = [
      row.run_id,
      row.best_submission_id,
      row.agent,
      row.provider,
      row.model,
      row.suite,
      row.reasoning_effort,
      row.classification,
    ].filter(Boolean).join(' ').toLowerCase();
    return (!query || haystack.includes(query)) && (!state.suite || row.suite === state.suite);
  });

  return rows.sort((a, b) => {
    if (state.sort === 'reliability') return reliabilityOf(b) - reliabilityOf(a);
    if (state.sort === 'speed') return (medianTimeOf(a) ?? Infinity) - (medianTimeOf(b) ?? Infinity);
    if (state.sort === 'tokens') return (tokenEfficiencyOf(b) ?? -1) - (tokenEfficiencyOf(a) ?? -1);
    if (state.sort === 'value') return (valueOf(b) ?? -1) - (valueOf(a) ?? -1);
    if (state.sort === 'raw') return rawOf(b) - rawOf(a);
    return scoreOf(b) - scoreOf(a);
  });
}

function bestRow() {
  return dedupe(sourceRows()).sort((a, b) => scoreOf(b) - scoreOf(a))[0] || state.latest || {};
}

function pageHead(kicker, title, body, aside = '') {
  document.title = `${title} | HermesBench`;
  return `<section class="page-head${aside ? '' : ' full'}">
    <div><span class="crumb">${escapeHtml(kicker)}</span><h1>${escapeHtml(title)}</h1><p class="lede">${escapeHtml(body)}</p></div>
    ${aside}
  </section>`;
}

function metricRow(label, value, sub = '', cls = '') {
  return `<div class="metric-row ${cls}"><span>${escapeHtml(label)}${sub ? `<br><small>${escapeHtml(sub)}</small>` : ''}</span><b>${value}</b></div>`;
}

function miniMetric(label, value) {
  return `<div class="mini-metric"><b>${value}</b><span>${escapeHtml(label)}</span></div>`;
}

function tag(label, hot = false) {
  return `<span class="tag${hot ? ' hot' : ''}">${escapeHtml(label)}</span>`;
}

function fold(title, body, open = false) {
  return `<details ${open ? 'open' : ''}><summary>${escapeHtml(title)}</summary><div class="fold-body">${body}</div></details>`;
}

function emptyState(title, body, action = '') {
  return `<section class="empty-state"><h2>${escapeHtml(title)}</h2><p>${escapeHtml(body)}</p>${action}</section>`;
}

function backLink(label = 'Back to leaderboard', href = '#/leaderboard') {
  return `<p class="back-link"><a class="text-pill" href="${href}">${escapeHtml(label)}</a></p>`;
}

function heroReceipt(row) {
  return `<aside class="receipt" aria-label="Best public sample receipt">
    <div class="receipt-inner">
      <div class="receipt-top"><span>public sample</span><span>${escapeHtml(statusLabel(row))}</span></div>
      <div class="receipt-score"><span>${fmt.pct(scoreOf(row))}</span></div>
      <div class="receipt-line"><span>model</span><b>${escapeHtml(modelLabel(row))}</b></div>
      <div class="receipt-line"><span>tasks passed</span><b>${fmt.num(passedOf(row))}/${fmt.num(taskCountOf(row))}</b></div>
      <div class="receipt-line"><span>false done</span><b>${fmt.num(falseDoneCountOf(row))}</b></div>
      <div class="receipt-line"><span>median time</span><b>${fmt.seconds(medianTimeOf(row))}</b></div>
      <div class="receipt-foot">run ${escapeHtml(runIdOf(row) || 'n/a')}</div>
    </div>
  </aside>`;
}

function homePage() {
  const all = dedupe(sourceRows());
  const best = bestRow();
  return `<section class="hero">
    <div>
      <span class="crumb">proof, not posture</span>
      <h1>Did the agent actually do the work?</h1>
      <p class="lede">HermesBench gives agents real tool-using tasks, then checks files, logs, commands, tests, and final claims.</p>
      <div class="hero-actions"><a class="btn primary" href="#/leaderboard">Compare runs</a><a class="btn secondary" href="#/methodology">Read scoring</a></div>
    </div>
    ${heroReceipt(best)}
  </section>
  <section class="stat-wall" aria-label="Benchmark summary">
    <div class="stat"><b>${fmt.num(taskStats.total)}</b><span>tasks across public, fresh, anchor, private, and long-horizon packs</span></div>
    <div class="stat"><b>${fmt.num(all.length)}</b><span>public sample runs currently visible in this static site</span></div>
    <div class="stat"><b>${fmt.pct(reliabilityOf(best))}</b><span>best-run reliability after false-done and timeout pressure</span></div>
    <div class="stat"><b>${fmt.compact(tokenCountOf(best))}</b><span>tokens spent by the current top public sample</span></div>
  </section>
  <section class="split-section">
    <div class="section-title"><h2>The benchmark is a receipt checker.</h2><p>Normal leaderboards reward answers. HermesBench rewards completed work with a trail you can inspect.</p></div>
    <div class="evidence-list">
      ${evidenceRow('01', 'Execution first', 'Tasks require reading files, changing files, running commands, inspecting output, and leaving artifacts.')}
      ${evidenceRow('02', 'False-done pressure', 'A confident final answer is not enough. If evidence is missing, the task can fail even when the prose sounds good.')}
      ${evidenceRow('03', 'Run-level audits', 'Every public run can expose task status, checks, tokens, tool calls, timing, and model settings like reasoning effort.')}
      ${evidenceRow('04', 'Public samples, private rankings', 'The visible runs help development. Cleaner official rankings need private and fresh task packs too.')}
    </div>
  </section>
  <section class="wide-callout"><h2>One screen, one question.</h2><p>The redesign splits the site into focused surfaces: overview, comparison, task catalog, scoring, run instructions, and per-run evidence. No mega-table as the default read.</p><a class="text-pill" href="#/tasks">Inspect task packs</a></section>`;
}

function evidenceRow(number, title, body) {
  return `<article class="evidence-row"><code>${number}</code><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(body)}</p></div></article>`;
}

function controls() {
  const suites = [...new Set(sourceRows().map((row) => row.suite).filter(Boolean))].sort();
  return `<section class="toolbar" aria-label="Leaderboard controls">
    <label class="control"><span>Find</span><input id="filter" type="search" autocomplete="off" placeholder="deepseek, gpt, high" value="${escapeHtml(state.filter)}"></label>
    <label class="control"><span>Suite</span><select id="suite"><option value="">All task sets</option>${suites.map((suite) => `<option value="${escapeHtml(suite)}" ${state.suite === suite ? 'selected' : ''}>${escapeHtml(suite)}</option>`).join('')}</select></label>
    <label class="control"><span>Sort</span><select id="sort">
      ${[
        ['score', 'Best score'],
        ['reliability', 'Reliability'],
        ['speed', 'Fastest'],
        ['tokens', 'Token efficiency'],
        ['value', 'Value'],
        ['raw', 'Raw score'],
      ].map(([value, label]) => `<option value="${value}" ${state.sort === value ? 'selected' : ''}>${label}</option>`).join('')}
    </select></label>
  </section>`;
}

function podium(rows) {
  const top = rows[0];
  if (!top) return '';
  return `<section class="podium" aria-label="Top visible run">
    <article class="podium-main">
      <span class="rank-tag hot">#1 ${escapeHtml(statusLabel(top))}</span>
      <h2>${escapeHtml(modelTitle(top))}</h2>
      <p class="muted">${escapeHtml(providerLine(top))} with run id <span class="mono">${escapeHtml(runIdOf(top) || 'n/a')}</span>.</p>
      <div class="score-figure"><b>${fmt.pct(scoreOf(top))}</b><span>${fmt.num(passedOf(top))}/${fmt.num(taskCountOf(top))} tasks passed</span></div>
      <div class="hero-actions"><a class="btn primary" href="#/runs/${encodeURIComponent(runIdOf(top))}">Open evidence</a><a class="btn secondary" href="#/models/${encodeURIComponent(top.provider || 'unknown')}/${encodeURIComponent(top.model || 'unknown')}">Model history</a></div>
    </article>
    <aside class="podium-side">
      ${metricRow('false done', fmt.num(falseDoneCountOf(top)), 'claims without proof')}
      ${metricRow('timeouts', fmt.num(timeoutCountOf(top)), 'unfinished tasks')}
      ${metricRow('median task time', fmt.seconds(medianTimeOf(top)), 'wall clock')}
      ${metricRow('token efficiency', fmt.num(tokenEfficiencyOf(top), 3), 'score per 1m tokens')}
    </aside>
  </section>`;
}

function runCard(row, index) {
  const runId = runIdOf(row);
  return `<article class="run-card">
    <div class="rank-number">${String(index + 1).padStart(2, '0')}</div>
    <div class="run-title"><h2>${escapeHtml(modelTitle(row))}</h2><p>${escapeHtml(statusLabel(row))} / ${escapeHtml(providerLine(row))} / <span class="mono">${escapeHtml(runId || 'n/a')}</span></p></div>
    <div class="mini-metrics">
      ${miniMetric('score', fmt.pct(scoreOf(row)))}
      ${miniMetric('passed', `${fmt.num(passedOf(row))}/${fmt.num(taskCountOf(row))}`)}
      ${miniMetric('false done', fmt.num(falseDoneCountOf(row)))}
    </div>
    <div class="hero-actions" style="grid-column: 1 / -1; margin-top: 0"><a class="text-pill" href="#/runs/${encodeURIComponent(runId)}">Task report</a><a class="text-pill" href="#/models/${encodeURIComponent(row.provider || 'unknown')}/${encodeURIComponent(row.model || 'unknown')}">Model history</a></div>
  </article>`;
}

function leaderboardPage() {
  const rows = currentRows();
  return `${pageHead('leaderboard', 'Who finished the most real work?', 'Sort by score, reliability, speed, token efficiency, or value. Public samples are useful evidence, not final official rankings.', `<aside class="panel">${metricRow('visible runs', fmt.num(rows.length))}${metricRow('task sets', fmt.num(new Set(sourceRows().map((r) => r.suite)).size))}${metricRow('best score', fmt.pct(scoreOf(rows[0] || {})))}</aside>`)}
  ${controls()}
  ${rows.length ? `${podium(rows)}<section class="run-list" id="leaderboard-results" aria-live="polite">${rows.map(runCard).join('')}</section>` : emptyState('No matching runs', 'Try a broader model name or clear the task-set filter.', '<button class="btn secondary" type="button" data-reset>Clear filters</button>')}
  ${fold('How should I read this?', '<p>Start with tasks passed and false-done count. Speed and token use matter after the run proves it actually completed the task.</p>')}
  ${fold('Why not call these official rankings?', '<p>The public sample runs are visible and therefore gameable. Official rankings should mix private holdouts and fresh task waves.</p>')}`;
}

function tasksPage() {
  return `${pageHead('task catalog', 'What work does HermesBench ask agents to do?', 'The task catalog is built around concrete agent failure modes: skipping files, claiming success too early, losing context, timing out, or failing to verify output.')}
  <section class="task-grid">
    ${taskStats.packs.map(([name, id, count, body]) => `<article class="task-pack"><div>${tag(id, id === 'public-dev')}<h2>${escapeHtml(name)}</h2><p>${escapeHtml(body)}</p></div><b class="score-figure" style="margin:0"><span class="accent">${escapeHtml(count)}</span><span>tasks</span></b></article>`).join('')}
  </section>
  <section class="wide-callout"><h2>Tasks are small, but not toy prompts.</h2><p>They exercise the whole agent loop: read, decide, act, check, recover, and report honestly.</p><div class="tag-cloud">${taskStats.categories.map((category) => tag(category)).join('')}</div></section>
  ${fold('What does a task include?', '<p>A task has setup files, instructions, scoring checks, cleanup notes, metadata, and expected artifacts. Long-horizon tasks add staged work and compaction pressure.</p>')}`;
}

function methodologyPage() {
  return `${pageHead('scoring', 'How does a run pass?', 'The benchmark checks evidence first. If the artifact is missing or the verifier fails, the task fails no matter how polished the final answer sounds.')}
  <section class="method-list">
    ${methodItem('Task checks', 'Each task defines objective checks such as required files, command output, JSON fields, tests, summaries, or policy constraints.')}
    ${methodItem('Score', 'The overall score is the share of task credit earned after penalties and verifier failures.')}
    ${methodItem('False done', 'A false-done failure means the agent claimed or implied success without enough evidence. This is tracked separately because it is a common production failure.')}
    ${methodItem('Reliability', 'Reliability drops when a run times out or falsely claims completion. It separates careful agents from fast but sloppy agents.')}
    ${methodItem('Efficiency', 'Time, tokens, tool calls, and cost help explain how much effort the agent spent after the work is proven.')}
  </section>
  ${fold('What should not be compared?', '<p>Do not compare one public sample as if it were a complete model ranking. Compare suite, task visibility, reasoning effort, tool access, cost, time, and evidence quality.</p>', true)}`;
}

function methodItem(title, body) {
  return `<article class="method-item"><div><h2>${escapeHtml(title)}</h2><p>${escapeHtml(body)}</p></div></article>`;
}

const providerModels = {
  'openai-codex': ['gpt-5.5', 'gpt-5.1', 'gpt-5', 'o4-mini'],
  openrouter: ['deepseek/deepseek-v4-flash', 'mistralai/mistral-nemo', 'qwen/qwen3-235b-a22b', 'anthropic/claude-sonnet-4.5'],
  anthropic: ['claude-sonnet-4.5', 'claude-opus-4.1'],
  google: ['gemini-2.5-pro', 'gemini-2.5-flash'],
  local: ['qwen3.5-9b', 'llama.cpp/local-model'],
  custom: ['provider/model'],
};
const reasoningOptions = ['none', 'minimal', 'low', 'medium', 'high', 'xhigh'];
const suiteOptions = ['public-dev', 'long-horizon-dev', 'anchor', 'fresh-rolling', 'private-holdout'];

function shellArg(value) {
  const s = String(value ?? '');
  if (!s) return "''";
  return /^[A-Za-z0-9_./:=@+-]+$/.test(s) ? s : `'${s.replaceAll("'", "'\\''")}'`;
}

function slugPart(value) {
  return String(value || 'run').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 72) || 'run';
}

function modelChoices(provider) {
  const fromRows = sourceRows()
    .filter((row) => row.provider === provider && row.model)
    .map((row) => row.model);
  return [...new Set([...(providerModels[provider] || []), ...fromRows])];
}

function optionList(values, selected) {
  return values.map((item) => {
    const value = Array.isArray(item) ? item[0] : item;
    const label = Array.isArray(item) ? item[1] : item;
    return `<option value="${escapeHtml(value)}" ${String(selected) === String(value) ? 'selected' : ''}>${escapeHtml(label)}</option>`;
  }).join('');
}

function defaultOutputDir(command = state.command) {
  const target = command.task ? command.task : command.suite;
  return `results/${[command.agent, command.provider, command.model, target, command.reasoning].map(slugPart).join('-')}`;
}

function commandLines(command = state.command) {
  const run = ['uv run hermesbench run'];
  if (command.agent === 'shell') {
    run.push('--agent shell', '--command ./my-agent-runner.sh');
  } else {
    run.push('--agent', shellArg(command.agent));
  }

  if (command.agent === 'hermes') {
    run.push('--provider', shellArg(command.provider));
    run.push('--model', shellArg(command.model));
    run.push('--reasoning-effort', shellArg(command.reasoning));
  }

  if (command.task.trim()) run.push('--task', shellArg(command.task.trim()));
  else run.push('--suite', shellArg(command.suite));

  run.push('--jobs', shellArg(command.jobs));
  run.push('--output-dir', shellArg(command.outputDir));

  const resultGlob = `${shellArg(command.outputDir)}/hermesbench-*.json`;
  const upload = ["HERMESBENCH_SUBMISSION_TOKEN='<maintainer-issued-token>'", 'uv run hermesbench upload', resultGlob, '--endpoint', shellArg(command.endpoint.trim() || defaultApiEndpoint)];

  return [
    'uv run hermesbench validate-tasks',
    run.join(' '),
    `uv run hermesbench score ${resultGlob}`,
    upload.join(' '),
  ];
}

function commandText(command = state.command) {
  return commandLines(command).join('\n');
}

function commandBuilder() {
  const c = state.command;
  const providers = [...new Set([...Object.keys(providerModels), ...sourceRows().map((row) => row.provider).filter(Boolean)])];
  return `<section class="command-builder" aria-label="HermesBench command builder">
    <div class="panel">
      <span class="crumb">command builder</span>
      <h2>Pick the run settings.</h2>
      <p class="muted">Choose the runner, provider, model, reasoning effort, suite, and output path. The exact command updates on the right.</p>
      <div class="builder-grid">
        <label class="control"><span>Runner</span><select id="cmd-agent">${optionList(['hermes', 'mock', 'shell'], c.agent)}</select></label>
        <label class="control"><span>Provider</span><select id="cmd-provider">${optionList(providers, c.provider)}</select></label>
        <label class="control wide"><span>Model</span><input id="cmd-model" list="cmd-models" value="${escapeHtml(c.model)}" autocomplete="off"><datalist id="cmd-models">${modelChoices(c.provider).map((model) => `<option value="${escapeHtml(model)}"></option>`).join('')}</datalist></label>
        <label class="control"><span>Reasoning</span><select id="cmd-reasoning">${optionList(reasoningOptions, c.reasoning)}</select></label>
        <label class="control"><span>Suite</span><select id="cmd-suite">${optionList(suiteOptions, c.suite)}</select></label>
        <label class="control"><span>Jobs</span><select id="cmd-jobs">${optionList(['auto', '1', '2', '4', '8'], c.jobs)}</select></label>
        <label class="control"><span>Specific task optional</span><input id="cmd-task" placeholder="hb-dev-001-sanity-basic-tool-use" value="${escapeHtml(c.task)}"></label>
        <label class="control wide"><span>Output directory</span><input id="cmd-output" value="${escapeHtml(c.outputDir)}"></label>
        <label class="control wide"><span>API route</span><input id="cmd-endpoint" placeholder="https://hermesbench.site/v1/results" value="${escapeHtml(c.endpoint || defaultApiEndpoint)}"></label>
      </div>
      <p class="builder-note" id="cmd-note">The generated command scores the raw result, then posts the sanitized submission to the HermesBench API route. Public uploads require a maintainer-issued submission token and remain unofficial by default.</p>
    </div>
    <aside class="command-preview">
      <div class="code-panel"><pre><code id="built-command">${escapeHtml(commandText(c))}</code></pre></div>
      <div class="command-actions"><button class="btn primary" type="button" id="copy-command">Copy command</button><button class="btn secondary" type="button" id="reset-command">Reset defaults</button></div>
      <p class="copy-status" id="copy-status" aria-live="polite"></p>
    </aside>
  </section>`;
}

function submitPage() {
  return `${pageHead('run locally', 'Build and submit an agent run.', 'Pick provider, model, reasoning effort, task set, and output path. The builder gives the exact run, score, and submission commands.')}
  ${commandBuilder()}
  <section class="split-section"><div class="section-title"><h2>Before submitting, prove the run.</h2><p>A useful submission includes exact model, provider, reasoning effort, tool access, suite, costs where available, and task-level evidence files.</p></div><div class="evidence-list">
    ${evidenceRow('A', 'Validate tasks', 'Task definitions should pass schema checks before a run starts.')}
    ${evidenceRow('B', 'Keep artifacts', 'Do not delete logs, generated files, transcripts, or verifier output needed for review.')}
    ${evidenceRow('C', 'Label settings', 'Provider, model, reasoning effort, and agent configuration should be explicit.')}
  </div></section>`;
}

function checksList(task) {
  const checks = Array.isArray(task.checks) ? task.checks : [];
  if (!checks.length) return '<p>No check-level evidence is included for this task.</p>';
  return `<ul class="check-list">${checks.slice(0, 80).map((check) => `<li class="${check.status === 'pass' ? 'ok' : check.status === 'fail' ? 'danger' : ''}"><b>${escapeHtml(check.status || 'check')}</b> ${escapeHtml(check.label || check.name || '')}</li>`).join('')}</ul>`;
}

function taskStatus(task) {
  if (task.timeout) return ['timeout', 'no'];
  if (task.false_done) return ['false done', 'no'];
  if (task.passed || task.status === 'pass' || task.status === 'passed') return ['passed', 'ok'];
  return [task.status || 'failed', 'no'];
}

function taskEvidenceList(tasks) {
  if (!tasks.length) return emptyState('No task evidence in this file', 'The summary loaded, but this public result does not include task-level checks.');
  return `<section class="task-list">${tasks.map((task) => {
    const [label, cls] = taskStatus(task);
    return `<details><summary><span class="task-summary"><span class="status ${cls}">${escapeHtml(label)}</span><span>${escapeHtml(task.task_id || 'task')}</span><span class="mono">${fmt.pct(task.score)}</span></span></summary><div class="fold-body">
      <div class="mini-metrics">
        ${miniMetric('time', fmt.seconds(task.wall_time_seconds))}
        ${miniMetric('tool calls', fmt.num(task.tool_calls))}
        ${miniMetric('tokens', fmt.compact(task.token_usage?.total_tokens))}
      </div>
      ${task.category ? `<p style="margin-top:12px">Category: <span class="mono">${escapeHtml(task.category)}</span></p>` : ''}
      ${checksList(task)}
    </div></details>`;
  }).join('')}</section>`;
}

async function loadRun(runId) {
  if (!runId) throw new Error('Missing run id');
  if (!state.runCache.has(runId)) {
    state.runCache.set(runId, await loadJson(`data/runs/${encodeURIComponent(runId)}.json`));
  }
  return state.runCache.get(runId);
}

async function runDetailPage(runId) {
  const run = await loadRun(runId);
  return `${backLink()}${pageHead('task report', `Run ${run.run_id}`, `${modelLabel(run)}. This page focuses on task evidence, not leaderboard decoration.`, `<aside class="panel">${metricRow('overall score', fmt.pct(run.overall_score ?? run.score_percentage))}${metricRow('passed', `${fmt.num(run.passed_task_count)}/${fmt.num(run.task_count)}`)}${metricRow('reasoning effort', escapeHtml(run.reasoning_effort || 'not labeled'))}</aside>`)}
  <section class="run-detail">
    <aside class="panel sticky-panel">
      <h2>Run receipt</h2>
      ${metricRow('false done', fmt.num(run.false_done_count), fmt.pct(run.false_done_rate))}
      ${metricRow('timeouts', fmt.num(run.timeout_count), fmt.pct(run.timeout_rate))}
      ${metricRow('median time', fmt.seconds(run.median_wall_time_seconds))}
      ${metricRow('tokens', fmt.compact(run.total_tokens ?? run.token_usage?.total_tokens))}
      ${metricRow('tool calls', fmt.num(run.tool_call_count))}
      ${run.source ? `<p class="microcopy">Source: <span class="mono">${escapeHtml(run.source)}</span></p>` : ''}
    </aside>
    <div>${taskEvidenceList(run.tasks || [])}</div>
  </section>`;
}

function modelPage(provider, encodedModel) {
  const model = decodeURIComponent(encodedModel || 'unknown');
  const decodedProvider = decodeURIComponent(provider || 'unknown');
  const modelRuns = dedupe(sourceRows()).filter((row) => (row.provider || 'unknown') === decodedProvider && (row.model || 'unknown') === model);
  return `${backLink()}${pageHead('model history', model, `Runs for provider ${decodedProvider}. Compare exact suites and reasoning effort before drawing conclusions.`)}
  ${modelRuns.length ? `<section class="run-list">${modelRuns.map(runCard).join('')}</section>` : emptyState('No matching model runs', 'The leaderboard data has no rows for this provider and model.')}`;
}

function privacyPage() {
  return `${pageHead('privacy', 'Privacy', 'HermesBench is a static benchmark site. It reads local JSON files from this deployment and does not need account data to view public samples.')}
  <section class="method-list">
    ${methodItem('Public run data', 'Visible JSON files may include task summaries, transcripts, tool counts, timing, and verifier output for published benchmark runs.')}
    ${methodItem('No private credentials', 'Public tasks are intended to run without private accounts. Official private holdouts should not publish hidden task content.')}
  </section>`;
}

function termsPage() {
  return `${pageHead('terms', 'Terms', 'Use public sample runs as development evidence, not as a final purchasing, safety, or model-quality claim.')}
  <section class="method-list">
    ${methodItem('Compare context', 'Scores are only meaningful with suite, task visibility, model, provider, reasoning effort, tool access, and cost context.')}
    ${methodItem('Do not overclaim', 'A public sample can be useful without being an official ranking. Treat it as evidence to inspect, not a badge to blindly trust.')}
  </section>`;
}

function notFoundPage(path) {
  document.title = 'Page not found | HermesBench';
  return emptyState('Page not found', `No HermesBench page exists for ${path}.`, '<a class="btn primary" href="#/">Go home</a>');
}

function navHtml() {
  return routes.map(([href, label]) => `<a href="#${href}" data-route="${href}">${escapeHtml(label)}</a>`).join('');
}

function setActive(path) {
  let active = routes.find(([href]) => path === href || (href !== '/' && path.startsWith(href)))?.[0];
  if (!active && (path.startsWith('/runs/') || path.startsWith('/models/'))) active = '/leaderboard';
  if (!active) active = '/';
  document.querySelectorAll('[data-route]').forEach((link) => link.classList.toggle('active', link.dataset.route === active));
}

function bindCommandBuilder() {
  const ids = {
    agent: 'cmd-agent',
    provider: 'cmd-provider',
    model: 'cmd-model',
    reasoning: 'cmd-reasoning',
    suite: 'cmd-suite',
    task: 'cmd-task',
    jobs: 'cmd-jobs',
    outputDir: 'cmd-output',
    endpoint: 'cmd-endpoint',
  };
  const get = (key) => document.getElementById(ids[key]);
  const preview = document.getElementById('built-command');
  if (!preview) return;

  function sync({ resetOutput = false, providerChanged = false } = {}) {
    for (const [key, id] of Object.entries(ids)) {
      const el = document.getElementById(id);
      if (el) state.command[key] = el.value;
    }
    if (providerChanged) {
      const choices = modelChoices(state.command.provider);
      if (choices.length && !choices.includes(state.command.model)) state.command.model = choices[0];
      state.command.outputDir = defaultOutputDir();
      render(false);
      return;
    }
    if (resetOutput) {
      state.command.outputDir = defaultOutputDir();
      if (get('outputDir')) get('outputDir').value = state.command.outputDir;
    }
    preview.textContent = commandText();
    const note = document.getElementById('cmd-note');
    if (note) {
      const runnerNote = state.command.agent === 'hermes'
        ? 'Hermes uses provider, model, and reasoning effort exactly as shown.'
        : `${state.command.agent} ignores provider/model/reasoning; only runner, suite/task, jobs, and output path matter.`;
      const submitNote = 'Upload posts the sanitized submission to the HermesBench API route.';
      note.textContent = `${runnerNote} ${submitNote}`;
    }
  }

  ['agent', 'model', 'reasoning', 'suite', 'task', 'jobs', 'endpoint'].forEach((key) => {
    const el = get(key);
    if (el) el.addEventListener('input', () => sync({ resetOutput: ['agent', 'model', 'reasoning', 'suite', 'task'].includes(key) }));
  });
  const provider = get('provider');
  if (provider) provider.addEventListener('change', () => sync({ providerChanged: true }));
  const output = get('outputDir');
  if (output) output.addEventListener('input', () => sync());

  const reset = document.getElementById('reset-command');
  if (reset) reset.addEventListener('click', () => {
    state.command = {
      agent: 'hermes',
      provider: 'openai-codex',
      model: 'gpt-5.5',
      reasoning: 'low',
      suite: 'public-dev',
      task: '',
      jobs: 'auto',
      outputDir: 'results/hermes-openai-codex-gpt-5.5-public-dev-low',
      endpoint: defaultApiEndpoint,
    };
    render(false);
  });

  const copy = document.getElementById('copy-command');
  if (copy) copy.addEventListener('click', async () => {
    const status = document.getElementById('copy-status');
    try {
      await navigator.clipboard.writeText(commandText());
      if (status) status.textContent = 'Copied.';
    } catch (_) {
      if (status) status.textContent = 'Copy failed; select the command text manually.';
    }
  });

  sync();
}

function bindControls() {
  const filter = document.getElementById('filter');
  const suite = document.getElementById('suite');
  const sort = document.getElementById('sort');
  if (filter) filter.addEventListener('input', (event) => { state.filter = event.target.value; render(false); });
  if (suite) suite.addEventListener('change', (event) => { state.suite = event.target.value; render(false); });
  if (sort) sort.addEventListener('change', (event) => { state.sort = event.target.value; render(false); });
  document.querySelectorAll('[data-reset]').forEach((button) => button.addEventListener('click', () => {
    state.filter = '';
    state.suite = '';
    state.sort = 'score';
    render(false);
  }));
}

function routePath() {
  return decodeURI((location.hash || '#/').slice(1) || '/');
}

async function routeContent(path) {
  if (path === '/') return homePage();
  if (path === '/leaderboard') return leaderboardPage();
  if (path === '/tasks') return tasksPage();
  if (path === '/methodology') return methodologyPage();
  if (path === '/submit') return submitPage();
  if (path === '/privacy') return privacyPage();
  if (path === '/terms') return termsPage();
  if (path.startsWith('/runs/')) return runDetailPage(decodeURIComponent(path.slice('/runs/'.length)));
  if (path.startsWith('/models/')) {
    const rest = path.slice('/models/'.length);
    const slash = rest.indexOf('/');
    if (slash !== -1) return modelPage(rest.slice(0, slash), rest.slice(slash + 1));
  }
  return notFoundPage(path);
}

async function render(shouldScroll = true) {
  const app = document.getElementById('app');
  const path = routePath();
  try {
    app.innerHTML = await routeContent(path);
  } catch (error) {
    document.title = 'Error | HermesBench';
    app.innerHTML = `<section class="error-screen"><span class="crumb">load error</span><h1>Evidence did not load.</h1><p class="lede">${escapeHtml(error.message)}</p><p><button class="btn primary" type="button" onclick="location.reload()">Reload</button></p></section>`;
  }
  setActive(path);
  bindControls();
  bindCommandBuilder();
  if (shouldScroll && state.lastPath !== path) window.scrollTo({ top: 0, behavior: 'smooth' });
  state.lastPath = path;
}

async function init() {
  document.getElementById('desktop-nav').innerHTML = navHtml();
  document.getElementById('mobile-nav').innerHTML = navHtml();
  try {
    const [leaderboard, latest] = await Promise.all([
      loadJson('data/leaderboard.json'),
      loadJson('data/latest-result.json').catch(() => null),
    ]);
    state.leaderboard = leaderboard;
    state.latest = latest;
  } catch (error) {
    document.getElementById('app').innerHTML = `<section class="error-screen"><span class="crumb">load error</span><h1>Benchmark data did not load.</h1><p class="lede">${escapeHtml(error.message)}</p></section>`;
    return;
  }
  window.addEventListener('hashchange', () => render(true));
  render(false);
}

init();
