async function loadJson(path){const r=await fetch(path); if(!r.ok) throw new Error(path); return r.json();}
function pct(x){return `${Math.round((x||0)*100)}%`;}
Promise.all([loadJson('data/demo-leaderboard.json'),loadJson('data/demo-result.json')]).then(([leader,result])=>{
 const body=document.querySelector('#leaderboard-table tbody');
 leader.entries.forEach(e=>{const tr=document.createElement('tr'); tr.innerHTML=`<td>${e.rank}</td><td>${e.agent}</td><td>${e.model}</td><td>${pct(e.overall_score)}</td><td>${pct(e.pass_at_1)}</td><td>${pct(e.false_done_rate)}</td><td>${e.official?'Official':'Unofficial'}</td>`; body.appendChild(tr);});
 const detail=document.querySelector('#result-detail');
 detail.innerHTML=`<p><span class="badge">${result.official?'Official':'Unofficial demo'}</span> <strong>${result.run_id}</strong> — overall ${pct(result.overall_score)}</p><div class="grid">${Object.entries(result.category_scores).map(([k,v])=>`<div class="card"><strong>${k}</strong><br>${pct(v)}</div>`).join('')}</div><h3>Task evidence</h3>${result.tasks.map(t=>`<div class="card"><strong>${t.task_id}</strong> ${t.status} score ${pct(t.score)}<br><span class="muted">false_done=${t.false_done}; timeout=${t.timeout}; tool_calls=${t.tool_calls}</span><ul>${t.evidence.map(e=>`<li>${e}</li>`).join('')}</ul></div>`).join('')}`;
}).catch(err=>{document.querySelector('#result-detail').textContent='Unable to load demo data: '+err.message;});
