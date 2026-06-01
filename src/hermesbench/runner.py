from __future__ import annotations
import json, shutil, subprocess, tempfile, time, uuid
from datetime import datetime, timezone
from pathlib import Path
from .tasks import discover_tasks
from .adapters import get_adapter
from .graders.deterministic import run_checks
from .schemas import TaskResult, RunResult
from .versions import resolve_version

ROOT=Path(__file__).resolve().parents[2]

def _copy_fixtures(task, workdir: Path):
    src=ROOT/'fixtures'/task.metadata['id']
    if src.exists(): shutil.copytree(src, workdir, dirs_exist_ok=True)

def run_benchmark(agent='mock', suite='public-dev', task_id=None, output_dir='results', model=None, command=None, benchmark_version=None) -> Path:
    version_info=resolve_version(benchmark_version)
    if benchmark_version and version_info['suite'] != suite: raise ValueError('benchmark version does not match selected suite')
    tasks=discover_tasks(suite, ROOT)
    if task_id: tasks=[t for t in tasks if t.metadata['id']==task_id]
    if not tasks: raise ValueError('no tasks selected')
    adapter=get_adapter(agent, model=model, command=command)
    out=Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    started=datetime.now(timezone.utc).isoformat(); results=[]
    for task in tasks:
        t0=time.time(); false_done=False; timeout=False
        with tempfile.TemporaryDirectory(prefix=f"hb-{task.metadata['id']}-") as td:
            wd=Path(td); _copy_fixtures(task, wd)
            try: ar=adapter.run_task(task, wd)
            except subprocess.TimeoutExpired:
                ar=None; timeout=True
            score,evidence=run_checks(wd, task.deterministic_checks)
            if ar and ar.claimed_done and score < 1.0: false_done=True
            status='passed' if score>=1.0 else ('timeout' if timeout else 'failed')
            results.append(TaskResult(task.metadata['id'], task.metadata['category'], status, score, score>=1.0, round(time.time()-t0,3), ar.tool_calls if ar else 0, ar.cost_usd if ar else None, false_done, timeout, evidence, {'transcript': ar.transcript[:4000] if ar else ''}))
    completed=datetime.now(timezone.utc).isoformat()
    run=RunResult('hermesbench.result.v1', uuid.uuid4().hex[:12], suite, agent, model, started, completed, results, {'task_count':len(results), 'public_output_redacts_hidden_checks': True, 'benchmark_version': version_info['version']})
    path=out/f"hermesbench-{run.run_id}.json"
    path.write_text(json.dumps(run.to_jsonable(), indent=2))
    return path
