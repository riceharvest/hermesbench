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
const apiEndpoint = 'https://www.benchcut.info/v1/results';
const leaderboardEndpoint = 'https://www.benchcut.info/v1/leaderboard';

const routes = [
  ['/', 'Dashboard'],
  ['/leaderboard', 'Models'],
  ['/tasks', 'Tasks'],
  ['/methodology', 'Method'],
];

const taskStats = {
  total: 38,
  hermesCore: 13,
  hermesExtended: 25,
  packs: [
    ['Hermes Core', 'hermes-core', '13', 'Tools and features shipped in the base Hermes Agent installation.'],
    ['Hermes Extended', 'hermes-extended', '25', 'Installable/configurable tools and integrations; unavailable tools are environment skips.'],
  ],
  categories: [
    'natural-tool-use', 'file', 'terminal', 'web', 'browser', 'browser_cdp', 'code_execution', 'vision', 'image_gen', 'video', 'video_gen', 'tts', 'memory', 'todo', 'skills', 'session_search', 'semantic_search', 'delegation', 'clarify', 'cronjob', 'computer_use', 'homeassistant', 'kanban', 'project', 'discord', 'discord_admin', 'x_search', 'yuanbao', 'spotify', 'feishu', 'messaging', 'stt', 'obsidian', 'github', 'docker', 'notion', 'linear', 'maps', 'himalaya', 'openhue'
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
    suite: 'hermes-core',
    task: '',
    jobs: 'auto',
    outputDir: 'results/hermes-openai-codex-gpt-5.5-hermes-core-low',
    endpoint: apiEndpoint,
  },
};

function isCapabilityData(leaderboard = state.leaderboard) {
  return Boolean(leaderboard?.capability_evidence) && leaderboard?.data_status !== 'no_data';
}

function isCapabilityRun(run) {
  return Boolean(run?.capability_evidence) && run?.evidence_class === 'official_evidence';
}

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
  if (!row.capability_evidence && row.data_status === 'live_api') return 'unreviewed submission';
  if (!row.capability_evidence) return 'unreviewed submission';
  return row.official || row.classification === 'official' ? 'official' : 'unreviewed submission';
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

function currentRows(leaderboard = state.leaderboard) {
  const query = state.filter.trim().toLowerCase();
  const rows = dedupe(sourceRows(leaderboard)).filter((row) => {
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
  return dedupe(sourceRows()).filter(isCapabilityRun).sort((a, b) => scoreOf(b) - scoreOf(a))[0] || {};
}

function pageHead(kicker, title, body, aside = '') {
  document.title = `${title} | BenchCut`;
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
  const rows = currentRows();
  const all = dedupe(sourceRows());
  const best = bestRow();
  const official = all.filter(isCapabilityRun);
  const suites = [...new Set(all.map((row) => row.suite).filter(Boolean))];
  const officialRuns = official.length;
  const visibleRows = rows.slice(0, 6);
  document.title = 'Dashboard | BenchCut';
  return `<section class="data-header">
    <div><span class="crumb">benchcut / benchmark index</span><h1>Agent benchmark dashboard</h1></div>
    <div class="data-header-meta"><span class="live-dot"></span><b>${officialRuns ? 'official data' : 'awaiting official data'}</b><span>updated on request</span></div>
  </section>
  <section class="dashboard-toolbar" aria-label="Dashboard controls">
    <span class="dashboard-label">BenchCut / capability probes</span>
    <span class="toolbar-status">${fmt.num(taskStats.total)} tasks</span>
    <span class="toolbar-status">${fmt.num(suites.length)} suites</span>

  </section>
  <section class="data-grid metrics-grid" aria-label="Benchmark metrics">
    ${dashboardMetric('Published runs', fmt.num(officialRuns), 'official evidence')}
    ${dashboardMetric('Task coverage', fmt.num(taskStats.total), 'capability probes')}
    ${dashboardMetric('Best score', officialRuns ? fmt.pct(scoreOf(best)) : 'n/a', 'verified only')}
    ${dashboardMetric('Reliability', officialRuns ? fmt.pct(reliabilityOf(best)) : 'n/a', 'false done + timeout')}
    ${dashboardMetric('Median time', officialRuns ? fmt.seconds(medianTimeOf(best)) : 'n/a', 'best visible run')}
    ${dashboardMetric('Data status', officialRuns ? 'ready' : 'staging', officialRuns ? 'reviewed sample' : 'no public sample')}
  </section>
  <section class="dashboard-columns">
    <div class="dashboard-main">
      <div class="section-bar"><div><span class="crumb">comparison</span><h2>Model performance</h2></div><a class="text-pill" href="#/leaderboard">View all models</a></div>
      ${visibleRows.length ? `<div class="compact-table" role="table" aria-label="Top model runs"><div class="compact-table-head" role="row"><span>#</span><span>Model / config</span><span>Score</span><span>Passed</span><span>Reliability</span><span></span></div>${visibleRows.map((row, index) => dashboardRunRow(row, index)).join('')}</div>` : `<div class="data-empty"><b>No reviewed results are published yet.</b><span>Verified submissions will appear here after review.</span><a class="text-pill" href="#/submit">Submit a run</a></div>`}
    </div>
    <aside class="dashboard-side">
      <div class="section-bar"><div><span class="crumb">coverage</span><h2>Task packs</h2></div><a class="text-pill" href="#/tasks">All tasks</a></div>
      <div class="pack-list">${taskStats.packs.map(([name, id, count]) => `<a class="pack-row" href="#/tasks"><span><b>${escapeHtml(name)}</b><small>${escapeHtml(id)}</small></span><strong>${escapeHtml(count)}</strong></a>`).join('')}</div>
      <div class="side-note"><b>Evidence class</b><span>Only reviewed capability evidence contributes to model ranking.</span></div>
    </aside>
  </section>
  <section class="dashboard-foot"><span>Sources: official archived runs / task manifests</span><a href="#/methodology">Scoring methodology →</a></section>`;
}

function dashboardMetric(label, value, sub) {
  return `<div class="dashboard-metric"><span>${escapeHtml(label)}</span><b>${escapeHtml(value)}</b><small>${escapeHtml(sub)}</small></div>`;
}

function dashboardRunRow(row, index) {
  const runId = runIdOf(row);
  return `<a class="compact-table-row" role="row" href="#/runs/${encodeURIComponent(runId)}"><span class="table-rank">${String(index + 1).padStart(2, '0')}</span><span class="table-model"><b>${escapeHtml(modelTitle(row))}</b><small>${escapeHtml(providerLine(row))}</small></span><strong>${fmt.pct(scoreOf(row))}</strong><span>${fmt.num(passedOf(row))}/${fmt.num(taskCountOf(row))}</span><span>${fmt.pct(reliabilityOf(row))}</span><span class="row-arrow">→</span></a>`;
}

function evidenceRow(number, title, body) {
  return `<article class="evidence-row"><code>${number}</code><div><h3>${escapeHtml(title)}</h3><p>${escapeHtml(body)}</p></div></article>`;
}

function controls(leaderboard = state.leaderboard) {
  const suites = [...new Set(sourceRows(leaderboard).map((row) => row.suite).filter(Boolean))].sort();
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
  if (!isCapabilityData()) return '';
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
  const capability = isCapabilityData();
  if (!rows.length) {
    return `${pageHead('leaderboard', 'Runs', 'Sort verified work by score, reliability, speed, efficiency, or value.', `<aside class="panel">${metricRow('visible runs', '0')}${metricRow('status', 'awaiting data')}</aside>`)}
    ${emptyState('No published runs', 'No reviewed benchmark runs are currently published.')}`;
  }
  return `${pageHead('leaderboard', 'Runs', 'Verified work, ranked by the metric you choose.', `<aside class="panel">${metricRow('visible runs', fmt.num(rows.length))}${metricRow('task sets', fmt.num(new Set(sourceRows().map((r) => r.suite)).size))}${metricRow('best score', fmt.pct(scoreOf(rows[0] || {})))}</aside>`)}
  ${controls(state.leaderboard)}
  ${podium(rows)}<section class="run-list" id="leaderboard-results" aria-live="polite">${rows.map(runCard).join('')}</section>
  ${fold('How should I read this?', '<p>Start with tasks passed and false-done count. Speed and token use matter after the run proves it actually completed the task.</p>')}`;
}

function tasksPage() {
  return `${pageHead('task catalog', 'What work does BenchCut ask agents to do?', 'The task catalog is built around concrete agent failure modes: skipping files, claiming success too early, losing context, timing out, or failing to verify output.')}
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
const suiteOptions = [
  ['hermes-core', 'Hermes Core (default)'],
  ['hermes-extended', 'Hermes Extended (configured services required)'],
];

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
  return [
    'uv run hermesbench validate-tasks',
    run.join(' '),
    `uv run hermesbench score ${resultGlob}`,
  ];
}

function commandText(command = state.command) {
  return commandLines(command).join('\n');
}

function commandBuilder() {
  const c = state.command;
  const providers = [...new Set([...Object.keys(providerModels), ...sourceRows().map((row) => row.provider).filter(Boolean)])];
  return `<section class="command-builder" aria-label="BenchCut command builder">
    <div class="panel">
      <span class="crumb">command builder</span>
      <h2>Pick the run settings.</h2>
      <p class="muted">Core CLI is the default. Integrations require configured services, credentials, or local tooling; unavailable integration tasks are environment skips, not model failures.</p>
      <div class="builder-grid">
        <label class="control"><span>Runner</span><select id="cmd-agent">${optionList(['hermes', 'shell'], c.agent)}</select></label>
        <label class="control"><span>Provider</span><select id="cmd-provider">${optionList(providers, c.provider)}</select></label>
        <label class="control wide"><span>Model</span><input id="cmd-model" list="cmd-models" value="${escapeHtml(c.model)}" autocomplete="off"><datalist id="cmd-models">${modelChoices(c.provider).map((model) => `<option value="${escapeHtml(model)}"></option>`).join('')}</datalist></label>
        <label class="control"><span>Reasoning</span><select id="cmd-reasoning">${optionList(reasoningOptions, c.reasoning)}</select></label>
        <label class="control"><span>Suite</span><select id="cmd-suite">${optionList(suiteOptions, c.suite)}</select></label>
        <label class="control"><span>Jobs</span><select id="cmd-jobs">${optionList(['auto', '1', '2', '4', '8'], c.jobs)}</select></label>
        <label class="control"><span>Specific task optional</span><input id="cmd-task" placeholder="hbo-dev-001-project-board-recovery" value="${escapeHtml(c.task)}"></label>
        <label class="control wide"><span>Output directory</span><input id="cmd-output" value="${escapeHtml(c.outputDir)}"></label>
      </div>
      <p class="builder-note" id="cmd-note">The generated command validates, runs, and scores the benchmark locally. Public submissions are currently paused.</p>
    </div>
    <aside class="command-preview">
      <div class="code-panel"><pre><code id="built-command">${escapeHtml(commandText(c))}</code></pre></div>
      <div class="command-actions"><button class="btn primary" type="button" id="copy-command">Copy command</button><button class="btn secondary" type="button" id="reset-command">Reset defaults</button></div>
      <p class="copy-status" id="copy-status" aria-live="polite"></p>
    </aside>
  </div></section>`;
}

function browserUploadForm() {
  return `<section class="wide-callout upload-form" style="margin-top: clamp(18px, 3vw, 36px)" aria-label="Browser upload">
    <h2>Browser upload (maintainers)</h2>
    <p>Upload a scored result JSON file directly. The token is sent via HTTP header and never stored or logged by this page.</p>
    <div class="builder-grid" style="margin-top: 16px">
      <label class="control wide"><span>Result file (JSON)</span><input type="file" id="upload-file" accept=".json,application/json"></label>
      <label class="control"><span>API endpoint</span><input id="upload-endpoint" value="${escapeHtml(apiEndpoint)}" readonly></label>
      <label class="control"><span>Submission token</span><input type="password" id="upload-token" placeholder="token from deployment settings" autocomplete="off" style="font-family:var(--mono)"></label>
    </div>
    <div class="command-actions" style="margin-top: 14px">
      <button class="btn primary" type="button" id="upload-submit">Upload result</button>
      <button class="btn secondary" type="button" id="upload-clear">Clear</button>
    </div>
    <p class="copy-status" id="upload-status" aria-live="polite">Select a scored JSON file and enter the submission token.</p>
  </section>`;
}

function submitPage() {
  return `${pageHead('run locally', 'Build and score an agent run.', 'Pick provider, model, reasoning effort, task set, and output path. Public submissions are currently paused.')}
  ${commandBuilder()}
  <section class="split-section"><div class="section-title"><h2>Submissions are paused.</h2><p>You can still run the benchmark locally and keep the scored result for maintainer review. Uploads will reopen when the leaderboard intake is ready.</p></div><div class="evidence-list">
    ${evidenceRow('A', 'Validate tasks', 'Task definitions should pass schema checks before a run starts.')}
    ${evidenceRow('B', 'Keep artifacts', 'Do not delete logs, generated files, transcripts, or verifier output needed for review.')}
    ${evidenceRow('C', 'Keep artifacts', 'Retain the result JSON and task-level evidence for later review.')}
    ${evidenceRow('D', 'Official evidence', 'Only maintainer-reviewed archives appear as capability evidence on the public site.')}
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

function taskEvidenceList(tasks, capability = true) {
  if (!tasks.length) return emptyState('No task evidence in this file', 'The summary loaded, but this public result does not include task-level checks.');
  return `<section class="task-list">${tasks.map((task) => {
    const [label, cls] = taskStatus(task);
    return `<details><summary><span class="task-summary"><span class="status ${cls}">${escapeHtml(label)}</span><span>${escapeHtml(task.task_id || 'task')}</span>${capability ? `<span class="mono">${fmt.pct(task.score)}</span>` : '<span class="mono">unreviewed</span>'}</span></summary><div class="fold-body">
      <div class="mini-metrics">
        ${capability ? `${miniMetric('time', fmt.seconds(task.wall_time_seconds))}${miniMetric('tool calls', fmt.num(task.tool_calls))}${miniMetric('tokens', fmt.compact(task.token_usage?.total_tokens))}` : '<p class="muted">Unreviewed submission; score, timing, token, and tool-call metrics are not verified.</p>'}
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
  const capability = isCapabilityRun(run);
  document.title = `Run ${run.run_id} | BenchCut`;
  const status = capability ? 'official evidence' : 'unreviewed submission';
  const metaRow = (label, value) => `<tr><th>${escapeHtml(label)}</th><td>${escapeHtml(value ?? 'n/a')}</td></tr>`;
  const overview = capability
    ? `<section class="wiki-section" id="overview"><h2>Overview</h2><p>This page records one ${escapeHtml(run.suite || 'benchmark')} evaluation of <b>${escapeHtml(modelLabel(run))}</b>. The score is an evidence summary; the task ledger below is the audit trail.</p><div class="wiki-stat-grid"><div><b>${fmt.pct(run.overall_score ?? run.score_percentage)}</b><span>overall score</span></div><div><b>${fmt.num(run.passed_task_count)}/${fmt.num(run.task_count)}</b><span>tasks passed</span></div><div><b>${fmt.pct(run.false_done_rate)}</b><span>false done</span></div><div><b>${fmt.seconds(run.median_wall_time_seconds)}</b><span>median time</span></div></div></section>`
    : `<section class="wiki-section" id="overview"><h2>Overview</h2><p>This submission has not been reviewed or promoted. It is shown for traceability only; competitive metrics are unavailable.</p></section>`;
  return `${backLink()}<article class="wiki-page">
    <header class="wiki-header"><span class="crumb">benchcut / run record</span><h1>${escapeHtml(run.run_id)}</h1><p class="wiki-lede">${escapeHtml(modelLabel(run))} · ${escapeHtml(status)} · ${escapeHtml(run.suite || 'benchmark run')}</p><div class="wiki-tags">${tag(status, capability)} ${run.provider ? tag(run.provider) : ''} ${run.reasoning_effort ? tag(`reasoning: ${run.reasoning_effort}`) : ''}</div></header>
    <div class="wiki-layout">
      <aside class="wiki-sidebar">
        <nav class="wiki-toc" aria-label="On this page"><b>Contents</b><a href="#overview" data-scroll-target="overview">Overview</a><a href="#configuration" data-scroll-target="configuration">Configuration</a><a href="#tasks" data-scroll-target="tasks">Task ledger</a><a href="#provenance" data-scroll-target="provenance">Provenance</a></nav>
        <section class="wiki-infobox"><div class="wiki-infobox-title">Run receipt</div>${metricRow('score', fmt.pct(run.overall_score ?? run.score_percentage))}${metricRow('passed', `${fmt.num(run.passed_task_count)}/${fmt.num(run.task_count)}`)}${metricRow('timeouts', fmt.num(run.timeout_count))}${metricRow('tokens', fmt.compact(run.total_tokens ?? run.token_usage?.total_tokens))}${metricRow('tool calls', fmt.num(run.tool_call_count))}</section>
      </aside>
      <div class="wiki-article">
        ${overview}
        <section class="wiki-section" id="configuration"><h2>Configuration</h2><table class="wiki-table"><tbody>${metaRow('Agent', run.agent)}${metaRow('Provider', run.provider)}${metaRow('Model', run.model)}${metaRow('Suite', run.suite)}${metaRow('Reasoning effort', run.reasoning_effort || 'not labeled')}${metaRow('Started', run.started_at)}${metaRow('Completed', run.completed_at)}${metaRow('Schema', run.raw_result_schema_version)}</tbody></table></section>
        <section class="wiki-section" id="tasks"><h2>Task ledger</h2><p class="wiki-muted">Expand a task to inspect timing, tool use, token counts, and verifier checks.</p>${taskEvidenceList(run.tasks || [], capability)}</section>
        <section class="wiki-section" id="provenance"><h2>Provenance</h2><p>Published records are sanitized before entering the site. Hidden checks, submission tokens, and local secrets are excluded.</p>${run.source ? `<p class="wiki-source"><b>Archive source</b><br><span class="mono">${escapeHtml(run.source)}</span></p>` : ''}</section>
      </div>
    </div>
  </article>`;
}

function modelPage(provider, encodedModel) {
  const model = decodeURIComponent(encodedModel || 'unknown');
  const decodedProvider = decodeURIComponent(provider || 'unknown');
  const modelRuns = dedupe(sourceRows()).filter((row) => (row.provider || 'unknown') === decodedProvider && (row.model || 'unknown') === model);
  return `${backLink()}${pageHead('model history', model, `Runs for provider ${decodedProvider}. Compare exact suites and reasoning effort before drawing conclusions.`)}
  ${modelRuns.length ? `<section class="run-list">${modelRuns.map(runCard).join('')}</section>` : emptyState('No matching model runs', 'The leaderboard data has no rows for this provider and model.')}`;
}

function privacyPage() {
  return `${pageHead('privacy', 'Privacy', 'BenchCut is a static benchmark site. It reads local JSON files from this deployment and does not need account data to view public samples.')}
  <section class="method-list">
    ${methodItem('Public run data', 'Visible JSON files may include task summaries, transcripts, tool counts, timing, and verifier output for published benchmark runs.')}
    ${methodItem('No private credentials', 'Public tasks are intended to run without private accounts. Official private packs, if used, should not publish hidden task content.')}
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
  document.title = 'Page not found | BenchCut';
  return emptyState('Page not found', `No BenchCut page exists for ${path}.`, '<a class="btn primary" href="#/">Go home</a>');
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
      note.textContent = `${runnerNote} Public submissions are currently paused.`;
    }
  }

  ['agent', 'model', 'reasoning', 'suite', 'task', 'jobs'].forEach((key) => {
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
      suite: 'hermes-core',
      task: '',
      jobs: 'auto',
      outputDir: 'results/hermes-openai-codex-gpt-5.5-hermes-core-low',
      endpoint: apiEndpoint,
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
  bindBrowserUpload();
}

function bindWikiToc() {
  document.querySelectorAll('[data-scroll-target]').forEach((link) => link.addEventListener('click', (event) => {
    event.preventDefault();
    const target = document.getElementById(link.dataset.scrollTarget);
    if (target) target.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }));
}

/**
 * Wire up the browser upload form on the /submit page.
 * Sends the selected JSON file and token to the API via X-Hermesbench-Submission-Token header.
 * The token is used in-memory only and never persisted, logged, or hardcoded.
 */
function bindBrowserUpload() {
  const submitBtn = document.getElementById('upload-submit');
  const clearBtn = document.getElementById('upload-clear');
  const fileInput = document.getElementById('upload-file');
  const tokenInput = document.getElementById('upload-token');
  const statusEl = document.getElementById('upload-status');
  if (!submitBtn || !statusEl) return;

  submitBtn.addEventListener('click', async () => {
    const file = fileInput?.files?.[0];
    const token = tokenInput?.value?.trim();
    if (!file) { statusEl.textContent = 'Select a result JSON file to upload.'; return; }
    if (!token) { statusEl.textContent = 'Enter the submission token from your deployment settings.'; return; }
    if (file.type && file.type !== 'application/json' && !file.name.endsWith('.json')) {
      statusEl.textContent = 'The selected file does not look like a JSON results file. Expected .json extension.';
      return;
    }
    statusEl.textContent = 'Uploading…';
    submitBtn.disabled = true;
    try {
      const text = await file.text();
      let payload;
      try { payload = JSON.parse(text); } catch (_) {
        statusEl.textContent = 'The selected file is not valid JSON. Check the file and try again.';
        submitBtn.disabled = false;
        return;
      }
      // Safety: validate basic shape before sending — must contain result.run_id or run_id
      if (!payload?.result?.run_id && !payload?.run_id) {
        statusEl.textContent = 'Payload does not look like a BenchCut result (missing run_id).';
        submitBtn.disabled = false;
        return;
      }
      const response = await fetch(apiEndpoint, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Hermesbench-Submission-Token': token,
        },
        body: text,
      });
      const result = response.ok ? null : await response.json().catch(() => null);
      if (response.ok) {
        statusEl.textContent = 'Upload accepted ✓ A new leaderboard fetch will show the entry.';
      } else {
        const errMsg = result?.error || `HTTP ${response.status} — server rejected the payload.`;
        statusEl.textContent = `Upload rejected: ${errMsg}`;
      }
    } catch (err) {
      statusEl.textContent = `Network error: ${err.message || 'upload failed'}`;
    } finally {
      submitBtn.disabled = false;
    }
  });

  if (clearBtn) clearBtn.addEventListener('click', () => {
    if (fileInput) fileInput.value = '';
    if (tokenInput) tokenInput.value = '';
    if (statusEl) statusEl.textContent = 'Cleared. Select a scored JSON file and enter the submission token.';
  });
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
    document.title = 'Error | BenchCut';
    app.innerHTML = `<section class="error-screen"><span class="crumb">load error</span><h1>Evidence did not load.</h1><p class="lede">${escapeHtml(error.message)}</p><p><button class="btn primary" type="button" onclick="location.reload()">Reload</button></p></section>`;
  }
  setActive(path);
  bindControls();
  bindCommandBuilder();
  bindWikiToc();
  if (shouldScroll && state.lastPath !== path) window.scrollTo({ top: 0, behavior: 'smooth' });
  state.lastPath = path;
}

/**
 * Normalize a /v1/leaderboard API response (shape: { entries: [...] })
 * into the frontend's expected enriched shape with provenance fields.
 *
 * Live API submissions are explicitly non-capability evidence; they carry
 * evidence_class: 'unofficial_submission' and capability_evidence: false
 * so the frontend's isCapabilityData()/isCapabilityRun() guards prevent
 * their use for competitive ranking, reliability, or "best" claims.
 */
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
  // Ensure individual entries never inherit a top-level default that contradicts their row-level markers.
  for (const group of ['entries', 'official', 'unofficial']) {
    for (const entry of shape[group] || []) {
      if (entry.capability_evidence == null) entry.capability_evidence = false;
      if (entry.evidence_class == null) entry.evidence_class = 'unofficial_submission';
    }
  }
  return shape;
}

async function loadLeaderboard() {
  // The committed archive is the homepage's canonical source. The API is for
  // live submissions and may legitimately be empty while intake is paused.
  try {
    const response = await fetch('/data/leaderboard.json', { cache: 'no-store' });
    if (response.ok) {
      return await response.json();
    }
  } catch (_) {
  }
  // Keep a live-API fallback for local/development builds without generated data.
  try {
    const response = await fetch(leaderboardEndpoint);
    if (response.ok) return normalizeApiToFrontendShape(await response.json());
  } catch (_) {
  }
  return {
    data_status: 'no_data',
    display_notice: 'No data loaded from API. Only reviewed official runs appear as capability evidence.',
    capability_evidence: false,
    entries: [],
    official: [],
    unofficial: [],
    model_summaries: null,
  };
}

async function init() {
  document.getElementById('desktop-nav').innerHTML = navHtml();
  document.getElementById('mobile-nav').innerHTML = navHtml();
  try {
    state.leaderboard = await loadLeaderboard();
  } catch (error) {
    document.getElementById('app').innerHTML = `<section class="error-screen"><span class="crumb">load error</span><h1>Benchmark data did not load.</h1><p class="lede">${escapeHtml(error.message)}</p></section>`;
    return;
  }
  window.addEventListener('hashchange', () => render(true));
  render(false);
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { isCapabilityData, isCapabilityRun, normalizeApiToFrontendShape };
} else {
  init();
}
