async function loadJson(path){const r=await fetch(path); if(!r.ok) throw new Error(path); return r.json();}
function pct(x,d=0){return x==null?'—':`${(Number(x)*100).toFixed(d)}%`;}
function num(x,d=0){return x==null?'—':Number(x).toLocaleString(undefined,{maximumFractionDigits:d,minimumFractionDigits:d});}
function money(x){return x==null?'—':`$${Number(x).toFixed(x<1?4:2)}`;}
function seconds(x){return x==null?'—':`${Number(x).toFixed(Number(x)<10?1:0)}s`;}
function modelName(e){return [e.provider,e.model].filter(Boolean).join('/')+(e.reasoning_effort?` · reasoning ${e.reasoning_effort}`:'');}
function valueOrDash(v,fmt){return v==null?'—':fmt(v);}
function escapeHtml(s){return String(s ?? '').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));}

const categories=['file operations','codebase navigation','bugfixes','issue triage','docs research','provider config','browser automation','CSV/data','logs','CVE triage','Docker/CI','cron','context recovery','memory boundary','email/calendar','mock APIs','false-done traps','cost/latency'];
const taskList=document.querySelector('#task-list');
if(taskList){categories.forEach(c=>{const div=document.createElement('div'); div.className='task-chip'; div.textContent=c; taskList.appendChild(div);});}

function normalizeSummaries(leader){
  const summaries=leader.model_summaries||[];
  if(summaries.length) return summaries;
  return (leader.entries||[]).map(e=>({...e,submission_count:1,best_score_percentage:e.score_percentage??e.overall_score,average_score_percentage:e.score_percentage??e.overall_score,score_ci95_low:null,score_ci95_high:null,best_submission_id:e.run_id,best_submission:e}));
}

let leaderboardState={leader:null,filter:'',suite:'',sort:'score'};
function scoreOf(e){return e.score_percentage??e.overall_score??e.average_score_percentage??e.best_score_percentage??0;}
function rawScoreOf(e){return e.raw_overall_score??e.raw_score_percentage??scoreOf(e);}
function filterSortRows(rows){
  const q=leaderboardState.filter.toLowerCase();
  return rows.filter(e=>{
    const hay=[e.run_id,e.agent,e.provider,e.model,e.model_key,e.suite,e.reasoning_effort].filter(Boolean).join(' ').toLowerCase();
    return (!q||hay.includes(q)) && (!leaderboardState.suite||e.suite===leaderboardState.suite);
  }).sort((a,b)=>{
    const key=leaderboardState.sort;
    if(key==='false_done') return (a.false_done_rate??1)-(b.false_done_rate??1);
    if(key==='time') return (a.total_execution_time_seconds??Infinity)-(b.total_execution_time_seconds??Infinity);
    if(key==='tokens') return (a.total_tokens??Infinity)-(b.total_tokens??Infinity);
    if(key==='raw') return rawScoreOf(b)-rawScoreOf(a);
    return scoreOf(b)-scoreOf(a);
  });
}
function renderSummaryCards(leader){
  const target=document.querySelector('#leaderboard-summary');
  if(!target) return;
  const summaries=filterSortRows(normalizeSummaries(leader)).slice(0,6);
  if(!summaries.length){target.innerHTML='<p class="muted">No leaderboard data matches the current filters.</p>';return;}
  target.innerHTML=summaries.map((s,i)=>{
    const official=Boolean(s.official);
    const model=[s.provider,s.model].filter(Boolean).join('/') || s.model_key || 'unknown model';
    const ci=s.score_ci95_low==null?'CI pending':`${pct(s.score_ci95_low,1)}–${pct(s.score_ci95_high,1)} 95% CI`;
    const runs=s.submission_count??1;
    const score=s.average_score_percentage??s.best_score_percentage??s.score_percentage??s.overall_score;
    const falseDone=s.average_false_done_rate??s.false_done_rate;
    const timeout=s.average_timeout_rate??s.timeout_rate;
    const time=s.average_total_execution_time_seconds??s.total_execution_time_seconds;
    const tokens=s.average_total_tokens??s.total_tokens;
    const tools=s.average_tool_call_count??s.tool_call_count;
    const cost=s.average_total_cost_usd??s.total_cost_usd??s.cost_usd;
    return `<article class="summary-card ${official?'official':''}">
      <span class="rank">${official?'Official':'Sample'} #${i+1}</span>
      <div class="model">${escapeHtml(model)}</div>
      <div class="meta">${escapeHtml(s.agent||'agent')} · ${runs} run${runs===1?'':'s'} · best ${escapeHtml(s.best_submission_id||s.run_id||'—')}</div>
      <div class="score-row"><span class="big-score">${pct(score)}</span><span class="ci">${ci}</span></div>
      <div class="metric-strip">
        <div class="metric"><b>${pct(falseDone)}</b><span>false done</span></div>
        <div class="metric"><b>${pct(timeout)}</b><span>timeout</span></div>
        <div class="metric"><b>${seconds(time)}</b><span>wall time</span></div>
        <div class="metric"><b>${money(cost)}</b><span>cost</span></div>
        <div class="metric"><b>${num(tokens)}</b><span>tokens</span></div>
        <div class="metric"><b>${num(tools)}</b><span>tools</span></div>
      </div>
    </article>`;
  }).join('');
}

function renderRuns(leader){
  const body=document.querySelector('#leaderboard-table tbody');
  if(!body) return;
  const rows=filterSortRows([...(leader.official||[]),...(leader.unofficial||[]),...(leader.entries||[])]);
  body.innerHTML='';
  if(!(leader.official||[]).length){
    const tr=document.createElement('tr');
    tr.innerHTML='<td colspan="10" class="muted">No official private/fresh-pack runs have been published yet. Rows below are public-dev smoke samples.</td>';
    body.appendChild(tr);
  }
  rows.forEach(e=>{
    const tr=document.createElement('tr');
    const score=e.score_percentage??e.overall_score;
    const raw=e.raw_overall_score??e.raw_score_percentage;
    const status=e.official?'Official private/fresh repeated run':'Single public-dev smoke sample';
    tr.innerHTML=`
      <td><span class="mono">${escapeHtml(e.run_id||'—')}</span><br><span class="small">${escapeHtml(e.suite||'public-dev')}</span></td>
      <td><strong>${escapeHtml(e.agent||'—')}</strong><br><span class="small">${escapeHtml(modelName(e)||'—')}</span></td>
      <td class="score" title="Effective score after penalties/gating used for ranking">${pct(score)}</td>
      <td title="Raw score before false-done or policy penalties">${pct(raw)}</td>
      <td>${pct(e.pass_at_1)}</td>
      <td class="${e.false_done_rate ? 'bad' : 'good'}">${pct(e.false_done_rate)}</td>
      <td class="hide-compact">${seconds(e.total_execution_time_seconds)}</td>
      <td class="hide-compact">${money(e.total_cost_usd??e.cost_usd)}</td>
      <td class="hide-compact">${num(e.total_tokens)}</td>
      <td class="hide-compact">${num(e.tool_call_count)}</td>
      <td><span class="status-pill ${e.official?'official':'sample'}">${escapeHtml(status)}</span></td>`;
    body.appendChild(tr);
  });
}

function renderResult(result){
  const detail=document.querySelector('#result-detail');
  if(!detail) return;
  const metricCards=[
    ['Overall',pct(result.overall_score)],['Total score',`${num(result.total_score,2)} / ${num(result.max_score)}`],['Raw score',pct(result.raw_overall_score)],['Pass@1',pct(result.pass_at_1)],
    ['False done',pct(result.false_done_rate)],['Timeout',pct(result.timeout_rate)],['Verification',pct(result.verification_compliance)],['Total time',seconds(result.total_execution_time_seconds)],
    ['Median task',seconds(result.median_wall_time_seconds)],['P95 task',seconds(result.p95_wall_time_seconds)],['Tool calls',num(result.tool_call_count)],['Avg tools/task',num(result.avg_tool_calls_per_task,1)],
    ['Total tokens',num(result.total_tokens)],['Input tokens',num(result.input_tokens)],['Output tokens',num(result.output_tokens)],['Cost',money(result.total_cost_usd??result.cost_usd)]
  ].map(([k,v])=>`<div class="mini"><strong>${escapeHtml(k)}</strong><span class="value">${escapeHtml(v)}</span></div>`).join('');
  const cats=Object.entries(result.category_scores||{}).sort((a,b)=>a[0].localeCompare(b[0])).slice(0,14).map(([k,v])=>`<div class="bar-row"><div class="bar-label">${escapeHtml(k)}</div><div class="bar"><div class="bar-fill" style="width:${Math.max(0,Math.min(100,Number(v||0)*100))}%"></div></div><div class="score">${pct(v)}</div></div>`).join('');
  const tasks=(result.tasks||[]).slice(0,6).map(t=>`<div class="mini"><strong>${escapeHtml(t.task_id)}</strong><span class="value">${pct(t.score)}</span><span class="small">${escapeHtml(t.status)} · false_done=${Boolean(t.false_done)} · timeout=${Boolean(t.timeout)} · tools=${num(t.tool_calls)}</span></div>`).join('');
  const modelLine=modelName(result);
  const raw=result.raw_overall_score==null?'Raw score unavailable':`Raw ${pct(result.raw_overall_score)} from ${num(result.raw_total_score,2)} / ${num(result.max_score)} before policy penalties; effective/ranked score is ${pct(result.score_percentage??result.overall_score)}.`;
  const source=result.source?`Source: ${escapeHtml(result.source)}`:'Source path unavailable in this export';
  const repro=`uv run hermesbench run --agent ${escapeHtml(result.agent||'mock')} --suite ${escapeHtml(result.suite||'public-dev')} --output-dir /tmp/hermesbench-results\nuv run hermesbench score /tmp/hermesbench-results/*.json`;
  detail.innerHTML=`<p><span class="pill">${result.official?'Official':'Unofficial demo'}</span> <strong>${escapeHtml(result.run_id)}</strong> — ${escapeHtml(modelLine)} — <span class="score">overall ${pct(result.overall_score)}</span></p><div class="explain"><strong>Score provenance:</strong> ${escapeHtml(raw)}<br>${source}</div><div class="result-grid">${metricCards}</div><h3 style="margin-top:28px">Category scores</h3><div class="category-bars">${cats}</div><h3 style="margin-top:28px">Task evidence sample</h3><div class="result-grid">${tasks}</div><div class="code repro"><code>${repro}</code></div>`;
}

function wireTabs(){
  const tabs=[...document.querySelectorAll('.tab')];
  const summary=document.querySelector('#leaderboard-summary');
  const table=document.querySelector('.table-wrap');
  tabs.forEach(tab=>tab.addEventListener('click',()=>{
    tabs.forEach(t=>{t.classList.toggle('active',t===tab);t.setAttribute('aria-selected',String(t===tab));});
    const view=tab.dataset.view;
    if(summary) summary.style.display=view==='summary'?'grid':'none';
    if(table) table.style.display=view==='runs'?'block':'none';
  }));
  if(table) table.style.display='none';
}

function wireControls(leader){
  leaderboardState.leader=leader;
  const suites=[...new Set([...(leader.entries||[]),...(leader.official||[]),...(leader.unofficial||[])].map(e=>e.suite).filter(Boolean))].sort();
  const suite=document.querySelector('#leaderboard-suite');
  if(suite && suite.options.length<=1) suites.forEach(s=>suite.add(new Option(s,s)));
  const rerender=()=>{renderSummaryCards(leader);renderRuns(leader);};
  const filter=document.querySelector('#leaderboard-filter');
  const sort=document.querySelector('#leaderboard-sort');
  if(filter) filter.addEventListener('input',()=>{leaderboardState.filter=filter.value;rerender();});
  if(suite) suite.addEventListener('change',()=>{leaderboardState.suite=suite.value;rerender();});
  if(sort) sort.addEventListener('change',()=>{leaderboardState.sort=sort.value;rerender();});
}

Promise.all([loadJson('data/leaderboard.json'),loadJson('data/latest-result.json')]).then(([leader,result])=>{
  renderSummaryCards(leader);
  renderRuns(leader);
  renderResult(result);
  wireTabs();
  wireControls(leader);
}).catch(err=>{document.querySelector('#result-detail').textContent='Unable to load demo data: '+err.message;});
