async function loadJson(path){const r=await fetch(path); if(!r.ok) throw new Error(path); return r.json();}
function pct(x){return `${Math.round((x||0)*100)}%`;}
const categories=['file operations','codebase navigation','bugfixes','issue triage','docs research','provider config','browser automation','CSV/data','logs','CVE triage','Docker/CI','cron','context recovery','memory boundary','email/calendar','mock APIs','false-done traps','cost/latency'];
const taskList=document.querySelector('#task-list');
if(taskList){categories.forEach(c=>{const div=document.createElement('div'); div.className='task-chip'; div.textContent=c; taskList.appendChild(div);});}
Promise.all([loadJson('data/demo-leaderboard.json'),loadJson('data/demo-result.json')]).then(([leader,result])=>{
 const body=document.querySelector('#leaderboard-table tbody');
 leader.entries.forEach(e=>{const tr=document.createElement('tr'); tr.innerHTML=`<td>${e.rank}</td><td><strong>${e.agent}</strong></td><td>${e.model}</td><td class="score">${pct(e.overall_score)}</td><td>${pct(e.pass_at_1)}</td><td class="${e.false_done_rate ? 'bad' : ''}">${pct(e.false_done_rate)}</td><td>${e.official?'Official':'Unofficial'}</td>`; body.appendChild(tr);});
 const detail=document.querySelector('#result-detail');
 const cats=Object.entries(result.category_scores||{}).slice(0,12).map(([k,v])=>`<div class="mini"><strong>${k}</strong><br><span class="score">${pct(v)}</span></div>`).join('');
 const tasks=(result.tasks||[]).slice(0,6).map(t=>`<div class="mini"><strong>${t.task_id}</strong><br>${t.status} · score ${pct(t.score)}<br><span class="muted">false_done=${t.false_done}; timeout=${t.timeout}; tool_calls=${t.tool_calls}</span></div>`).join('');
 detail.innerHTML=`<p><span class="pill">${result.official?'Official':'Unofficial demo'}</span> <strong>${result.run_id}</strong> — <span class="score">overall ${pct(result.overall_score)}</span></p><div class="result-grid">${cats}</div><h3 style="margin-top:22px">Task evidence sample</h3><div class="result-grid">${tasks}</div>`;
}).catch(err=>{document.querySelector('#result-detail').textContent='Unable to load demo data: '+err.message;});
