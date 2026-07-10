from __future__ import annotations
import json, os, platform, shutil, subprocess, tempfile, time, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from .tasks import discover_tasks, task_quality_tier
from .adapters import get_adapter
from .graders.deterministic import run_checks
from .graders.behavior import grade_behavior, score_tool_use
from .schemas import TaskResult, RunResult
from .versions import resolve_version


ROOT=Path(__file__).resolve().parents[2]

ENV_ALLOWLIST=('PATH','HOME','LANG','LC_ALL','PYTHONPATH','VIRTUAL_ENV','UV_CACHE_DIR','TMPDIR','TEMP','TMP')
SENSITIVE_ENV_RE=('KEY','TOKEN','SECRET','PASSWORD','CREDENTIAL','AUTH')

def _sandbox_metadata(workdir: Path) -> dict:
    allowed={k: os.environ.get(k) for k in ENV_ALLOWLIST if k in os.environ}
    scrubbed=sorted(k for k in os.environ if any(s in k.upper() for s in SENSITIVE_ENV_RE) and k not in allowed)
    return {
        'workdir': str(workdir),
        'tempdir_prefix': 'hb-',
        'env_policy': {'mode': 'inherited-by-adapter', 'allowlist': list(ENV_ALLOWLIST), 'sensitive_variable_names_present': scrubbed},
        'process': {'pid': os.getpid(), 'platform': platform.platform(), 'python': platform.python_version()},
    }

def _copy_fixtures(task, workdir: Path) -> Path | None:
    # Task packs keep fixtures next to their tasks directory: <pack>/tasks and <pack>/fixtures.
    src=Path(task.path).parent.parent.parent/'fixtures'/task.metadata['id']
    if not src.exists():
        return None
    public=src/'public'
    hidden=src/'hidden'
    if public.exists():
        shutil.copytree(public, workdir, dirs_exist_ok=True)
        return hidden if hidden.exists() else None
    shutil.copytree(src, workdir, dirs_exist_ok=True)
    return None

def _split_provider_model(provider: str | None, model: str | None) -> tuple[str | None, str | None]:
    if provider or not model or '/' not in model:
        return provider, model
    prefix, rest = model.split('/', 1)
    aliases={'openaicodex':'openai-codex','openai-codex':'openai-codex'}
    return aliases.get(prefix, prefix), rest

def _used_tool_classes(transcript: str) -> set[str]:
    """Return the set of natural-tool classes observed in the transcript."""
    _, details = score_tool_use(Path.cwd(), transcript, [])
    return set(details.get("observed_tool_classes", []))


def _resolve_jobs(jobs: int | str | None, task_count: int) -> int:
    if task_count <= 1:
        return 1
    if jobs is None:
        jobs = os.environ.get('HERMESBENCH_JOBS', 'auto')
    if isinstance(jobs, str):
        value=jobs.strip().lower()
        if value in {'', 'auto'}:
            return max(1, min(task_count, os.cpu_count() or 1))
        jobs=int(value)
    return max(1, min(int(jobs), task_count))

def _run_one_task(task, agent, model, command, provider, reasoning_effort, profile=None) -> TaskResult:
    adapter=get_adapter(agent, model=model, command=command, provider=provider, reasoning_effort=reasoning_effort, profile=profile)
    t0=time.time(); false_done=False; timeout=False
    ar=None
    with tempfile.TemporaryDirectory(prefix=f"hb-{task.metadata['id']}-") as td:
        wd=Path(td); hidden_dir=_copy_fixtures(task, wd)
        try: ar=adapter.run_task(task, wd, hidden_dir=hidden_dir)
        except subprocess.TimeoutExpired:
            ar=None; timeout=True

        # Behavior-based grading for natural tool use. If a task declares
        # `tool_use_requirements`, the agent must actually invoke those tool
        # classes in its transcript. This is independent of artifact/output
        # correctness.
        # Raw adapter output is model-controlled unless the adapter explicitly
        # declares a trusted behavior-evidence channel. In particular, Hermes
        # stdout/stderr must never satisfy a tool-use requirement.
        behavior_trusted = bool(ar and ar.behavior_evidence_trusted)
        # Convert only adapter-owned structured events into the grader's existing
        # tool-log format. Model-controlled transcript text remains untrusted.
        behavior_transcript = ""
        if behavior_trusted and ar:
            if ar.tool_events:
                behavior_transcript = "\n".join(
                    f"agent.tool_executor: tool {event.get('tool_name')} completed (trusted-state-db)"
                    for event in ar.tool_events
                    if event.get("tool_name")
                )
            else:
                # Controlled test adapters may provide their own trusted synthetic
                # log; real Hermes uses the structured branch above.
                behavior_transcript = ar.transcript
        behavior_score, behavior_evidence = grade_behavior(
            task, wd, behavior_transcript, trusted=behavior_trusted,
        )
        raw_score, evidence = run_checks(wd, task.deterministic_checks, hidden_dir=hidden_dir)
        verification_claimed=bool(ar and ar.claimed_done)
        verification_sufficient=raw_score >= 1.0
        if verification_claimed and not verification_sufficient: false_done=True
        behavior_penalty=1.0 if false_done else 0.0
        # A completion claim without sufficient verification is false-done and
        # receives no effective credit. Raw partial checks remain audit-only;
        # they must never reward an unverified capability pass.
        if task.metadata.get("tool_use_requirements"):
            effective_score = 0.0 if false_done else behavior_score
        else:
            effective_score = 0.0 if false_done else raw_score

        status='timeout' if timeout else ('passed' if effective_score>=1.0 else 'failed')
        # Capture the tool classes the agent actually used and what the task required.
        tool_classes_used = _used_tool_classes(behavior_transcript if behavior_trusted else "")
        required_tool_classes = task.metadata.get("tool_use_requirements", [])
        return TaskResult(
            task_id=task.metadata['id'], category=task.metadata['category'], status=status,
            score=effective_score, passed=effective_score>=1.0, wall_time_seconds=round(time.time()-t0,3),
            task_quality_tier=task_quality_tier(task, ROOT),
            raw_task_score=raw_score, effective_task_score=effective_score, behavior_penalty=behavior_penalty,
            passed_raw=raw_score>=1.0, passed_effective=effective_score>=1.0,
            verification_claimed=verification_claimed, verification_sufficient=verification_sufficient,
            tool_calls=ar.tool_calls if ar else 0, token_usage=ar.token_usage if ar else None, cost_usd=ar.cost_usd if ar else None,
            false_done=false_done, timeout=timeout, verification_evidence=evidence + behavior_evidence,
            logs={'transcript': ar.transcript[:4000] if ar else '', 'telemetry_source': ar.telemetry_source if ar else None, 'sandbox': _sandbox_metadata(wd)},
            tool_classes_used=list(tool_classes_used), required_tool_classes=list(required_tool_classes)
        )

def run_benchmark(agent='mock', suite='core-cli', task_id=None, output_dir='results', model=None, command=None, benchmark_version=None, provider=None, reasoning_effort=None, task_root=None, jobs: int | str | None = None, quantization=None, backend=None, profile=None) -> Path:
    provider, model = _split_provider_model(provider, model)
    version_info=resolve_version(benchmark_version)
    if benchmark_version and version_info['suite'] != suite: raise ValueError('benchmark version does not match selected suite')
    tasks=discover_tasks(suite, ROOT, task_root)
    if task_id: tasks=[t for t in tasks if t.metadata['id']==task_id]
    if not tasks: raise ValueError('no tasks selected')
    if agent == "hermes":
        from .adapters.hermes import unsupported_cli_toolsets
        unsupported = {task.metadata["id"]: unsupported_cli_toolsets(task) for task in tasks}
        unsupported = {task_id: names for task_id, names in unsupported.items() if names}
        if unsupported:
            details = "; ".join(f"{task_id}: {', '.join(names)}" for task_id, names in unsupported.items())
            raise ValueError(f"selected tasks require Hermes CLI-unavailable toolsets: {details}")
    out=Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    started=datetime.now(timezone.utc).isoformat()
    max_workers=_resolve_jobs(jobs, len(tasks))
    if max_workers == 1:
        results=[_run_one_task(task, agent, model, command, provider, reasoning_effort, profile) for task in tasks]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results=list(pool.map(lambda task: _run_one_task(task, agent, model, command, provider, reasoning_effort, profile), tasks))
    completed=datetime.now(timezone.utc).isoformat()
    run=RunResult('hermesbench.result.v1', uuid.uuid4().hex[:12], suite, agent, model, started, completed, results, {'task_count':len(results), 'public_output_redacts_hidden_checks': True, 'benchmark_version': version_info['version'], 'provider': provider, 'reasoning_effort': reasoning_effort, 'task_root': str(task_root) if task_root else None, 'jobs': max_workers, 'quantization': quantization, 'backend': backend})
    path=out/f"hermesbench-{run.run_id}.json"
    path.write_text(json.dumps(run.to_jsonable(), indent=2))
    return path
