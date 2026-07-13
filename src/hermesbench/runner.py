from __future__ import annotations
import json, os, platform, re, shutil, subprocess, tempfile, time, uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .tasks import discover_tasks, task_quality_tier
from .adapters import get_adapter
from .graders.deterministic import run_checks
from .graders.behavior import grade_behavior, score_tool_use
from .schemas import TaskResult, RunResult, RunLedgerMetadata
from .versions import resolve_version


ROOT = Path(__file__).resolve().parents[2]

ENV_ALLOWLIST = (
    "PATH",
    "HOME",
    "LANG",
    "LC_ALL",
    "PYTHONPATH",
    "VIRTUAL_ENV",
    "UV_CACHE_DIR",
    "TMPDIR",
    "TEMP",
    "TMP",
)
SENSITIVE_ENV_RE = ("KEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL", "AUTH")
SENSITIVE_COMMAND_RE = re.compile(
    r"(?i)((?:\bapi[_-]?key|\btoken|\bsecret|\bpassword|\bcredential|\bauthorization)\b\s*(?:=|:|\s+)\s*|\bBearer\s+)[^\s,]+"
)


def _safe_command(command: str | None) -> str | None:
    """Return a command summary with obvious inline credentials redacted."""
    if command is None:
        return None
    return SENSITIVE_COMMAND_RE.sub(r"\1[REDACTED]", command)


def _sandbox_metadata(workdir: Path) -> dict:
    allowed = {k: os.environ.get(k) for k in ENV_ALLOWLIST if k in os.environ}
    scrubbed = sorted(
        k
        for k in os.environ
        if any(s in k.upper() for s in SENSITIVE_ENV_RE) and k not in allowed
    )
    return {
        "workdir": str(workdir),
        "tempdir_prefix": "hb-",
        "env_policy": {
            "mode": "inherited-by-adapter",
            "allowlist": list(ENV_ALLOWLIST),
            "sensitive_variable_names_present": scrubbed,
        },
        "process": {
            "pid": os.getpid(),
            "platform": platform.platform(),
            "python": platform.python_version(),
        },
    }


def _collect_git_commit() -> str | None:
    """Return the short git commit hash of the HermesBench checkout, or ``None``."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=ROOT,
        )
        if result.returncode == 0:
            commit = result.stdout.strip()
            return commit if commit else None
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return None


def _collect_git_dirty() -> bool | None:
    """Return whether the checkout differs from HEAD, including untracked files."""
    try:
        result = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=normal"],
            capture_output=True,
            text=True,
            timeout=5,
            cwd=ROOT,
        )
        if result.returncode == 0:
            return bool(result.stdout.strip())
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        pass
    return None


def _collect_system_metadata() -> dict[str, str | None]:
    """Collect safe OS/Python/platform metadata.

    Returns a dict suitable for direct inclusion in run metadata.  No GPU
    driver calls or privileged operations are performed.
    """
    info: dict[str, str | None] = {
        "os_platform": platform.platform(),
        "python_version": platform.python_version(),
    }
    # CPU info — parse /proc/cpuinfo if available (Linux); safe read-only.
    cpu_model: str | None = None
    cpu_count: str | None = None
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                line = line.strip()
                if line.startswith("model name") and cpu_model is None:
                    cpu_model = line.split(":", 1)[1].strip()
                if line.startswith("cpu cores") and cpu_count is None:
                    cpu_count = line.split(":", 1)[1].strip()
    except (FileNotFoundError, OSError):
        pass
    if cpu_model is None:
        cpu_model = platform.processor() or None
    if cpu_count is None:
        cpu_count = str(os.cpu_count() or 0)
    parts = []
    if cpu_model:
        parts.append(cpu_model)
    if cpu_count:
        parts.append(f"{cpu_count} cores")
    if parts:
        info["cpu_info"] = "; ".join(parts)

    # GPU info — safe discovery via nvidia-smi if on PATH, otherwise None.
    gpu_info: str | None = None
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,count", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if lines:
                # nvidia-smi returns one line per GPU; deduplicate model names.
                models: dict[str, int] = {}
                for line in lines:
                    name = line.rsplit(",", 1)[0].strip() if "," in line else line
                    models[name] = models.get(name, 0) + 1
                gpu_info = "; ".join(
                    f"{cnt}x {name}" if cnt > 1 else name
                    for name, cnt in models.items()
                )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        pass
    info["gpu_info"] = gpu_info
    return info


def _collect_run_metadata(
    provider: str | None,
    model: str | None,
    reasoning_effort: str | None,
    quantization: str | None,
    backend: str | None,
    profile: str,
    benchmark_version: str | None,
    jobs: int | None,
    run_wall_time_seconds: float | None,
    *,
    command: str | None = None,
) -> RunLedgerMetadata:
    """Build a ``RunLedgerMetadata`` from available parameters.

    Discovers system/platform/git metadata as side effect.  Use keyword
    arguments for optional provenance fields.
    """
    system = _collect_system_metadata()
    git_commit = _collect_git_commit()
    git_dirty = _collect_git_dirty()
    meta = RunLedgerMetadata(
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        quantization=quantization,
        backend=backend,
        profile=profile,
        benchmark_version=benchmark_version,
        jobs=jobs,
        run_wall_time_seconds=run_wall_time_seconds,
        os_platform=system.get("os_platform"),
        python_version=system.get("python_version"),
        cpu_info=system.get("cpu_info"),
        gpu_info=system.get("gpu_info"),
        git_commit=git_commit,
        git_dirty=git_dirty,
        command=_safe_command(command),
    )
    # Populate availability markers.
    avail: dict[str, bool] = {}
    avail["model_identity"] = bool(provider or model or reasoning_effort)
    avail["runtime"] = bool(profile or benchmark_version)
    avail["provenance"] = bool(git_commit or command) and git_dirty is not None
    avail["hardware"] = bool(system.get("cpu_info") or system.get("gpu_info"))
    avail["timing"] = run_wall_time_seconds is not None
    meta.metadata_available = avail
    return meta


def _copy_fixtures(task, workdir: Path) -> Path | None:
    # Task packs keep fixtures next to their tasks directory: <pack>/tasks and <pack>/fixtures.
    src = Path(task.path).parent.parent.parent / "fixtures" / task.metadata["id"]
    if not src.exists():
        return None
    public = src / "public"
    hidden = src / "hidden"
    if public.exists():
        shutil.copytree(public, workdir, dirs_exist_ok=True)
        return hidden if hidden.exists() else None
    shutil.copytree(src, workdir, dirs_exist_ok=True)
    return None


def _split_provider_model(
    provider: str | None, model: str | None
) -> tuple[str | None, str | None]:
    if provider or not model or "/" not in model:
        return provider, model
    prefix, rest = model.split("/", 1)
    aliases = {"openaicodex": "openai-codex", "openai-codex": "openai-codex"}
    return aliases.get(prefix, prefix), rest


def _used_tool_classes(transcript: str) -> set[str]:
    """Return the set of natural-tool classes observed in the transcript."""
    _, details = score_tool_use(Path.cwd(), transcript, [])
    return set(details.get("observed_tool_classes", []))


def _resolve_jobs(jobs: int | str | None, task_count: int) -> int:
    if task_count <= 1:
        return 1
    if jobs is None:
        jobs = os.environ.get("HERMESBENCH_JOBS", "auto")
    if isinstance(jobs, str):
        value = jobs.strip().lower()
        if value in {"", "auto"}:
            return max(1, min(task_count, os.cpu_count() or 1))
        jobs = int(value)
    return max(1, min(int(jobs), task_count))


def _run_one_task(
    task, agent, model, command, provider, reasoning_effort, profile=None,
    stall_idle_seconds=300.0,
) -> TaskResult:
    adapter = get_adapter(
        agent,
        model=model,
        command=command,
        provider=provider,
        reasoning_effort=reasoning_effort,
        profile=profile,
        stall_idle_seconds=stall_idle_seconds,
    )
    t0 = time.time()
    false_done = False
    timeout = False
    stalled = False
    ar = None
    with tempfile.TemporaryDirectory(prefix=f"hb-{task.metadata['id']}-") as td:
        wd = Path(td)
        hidden_dir = _copy_fixtures(task, wd)
        try:
            ar = adapter.run_task(task, wd, hidden_dir=hidden_dir)
        except subprocess.TimeoutExpired:
            ar = None
            timeout = True

        required_classes = set(task.metadata.get("tool_use_requirements", []))
        runtime_issues = set(ar.runtime_issues if ar else [])
        runtime_skip_reason = None
        if "computer_use" in required_classes and "computer_use_runtime_unavailable" in runtime_issues:
            runtime_skip_reason = "computer_use runtime unavailable: cua-driver MCP server error"
        elif "delegation" in required_classes and "delegation_provider_interrupted" in runtime_issues:
            runtime_skip_reason = "delegation runtime unavailable: child provider API interrupted"
        elif "vision" in required_classes and "vision_runtime_unavailable" in runtime_issues:
            runtime_skip_reason = "vision runtime unavailable: trusted vision tool result reported a server error"

        # Behavior-based grading for natural tool use. If a task declares
        # `tool_use_requirements`, the agent must actually invoke those tool
        # classes in its transcript. This is independent of artifact/output
        # correctness.
        # Raw adapter output is model-controlled unless the adapter explicitly
        # declares a trusted behavior-evidence channel. In particular, Hermes
        # stdout/stderr must never satisfy a tool-use requirement.
        behavior_trusted = bool(ar and ar.behavior_evidence_trusted)
        stalled = bool(ar and ar.stalled)
        # Convert only adapter-owned structured events into the grader's existing
        # tool-log format. Model-controlled transcript text remains untrusted.
        behavior_transcript = ""
        if behavior_trusted and ar:
            if ar.tool_events:
                behavior_transcript = "\n".join(
                    f"agent.tool_executor: tool {event.get('tool_name')} completed (trusted-state-db)"
                    for event in ar.tool_events
                    if event.get("tool_name") and event.get("succeeded", True)
                )
            else:
                # Controlled test adapters may provide their own trusted synthetic
                # log; real Hermes uses the structured branch above.
                behavior_transcript = ar.transcript
        behavior_score, behavior_evidence = grade_behavior(
            task,
            wd,
            behavior_transcript,
            trusted=behavior_trusted,
        )
        raw_score, evidence = run_checks(
            wd, task.deterministic_checks, hidden_dir=hidden_dir
        )
        if runtime_skip_reason and (raw_score < 1.0 or behavior_score < 1.0):
            return TaskResult(
                task_id=task.metadata["id"], category=task.metadata["category"],
                status="environment_skipped", score=0.0, passed=False,
                wall_time_seconds=round(time.time() - t0, 3),
                task_quality_tier=task_quality_tier(task, ROOT),
                raw_task_score=raw_score, effective_task_score=0.0,
                environment_skip=True, skip_reason=runtime_skip_reason,
                verification_evidence=evidence + behavior_evidence + [runtime_skip_reason],
                tool_calls=ar.tool_calls, token_usage=ar.token_usage, cost_usd=ar.cost_usd,
                logs={"transcript": ar.transcript[:4000], "tool_trace": ar.tool_events,
                      "telemetry_source": ar.telemetry_source, "sandbox": _sandbox_metadata(wd)},
                tool_classes_used=list(_used_tool_classes(behavior_transcript)),
                required_tool_classes=list(required_classes),
                runtime_issues=sorted(runtime_issues),
            )
        verification_claimed = bool(ar and ar.claimed_done)
        verification_sufficient = raw_score >= 1.0
        if verification_claimed and not verification_sufficient:
            false_done = True
        behavior_penalty = 1.0 if false_done else 0.0
        # A completion claim without sufficient verification is false-done and
        # receives no effective credit. Raw partial checks remain audit-only;
        # they must never reward an unverified capability pass.
        if task.metadata.get("tool_use_requirements"):
            effective_score = (
                1.0
                if not false_done and raw_score >= 1.0 and behavior_score >= 1.0
                else 0.0
            )
        else:
            effective_score = 0.0 if false_done else raw_score

        status = (
            "timeout" if timeout else
            ("stalled" if stalled else ("passed" if effective_score >= 1.0 else "failed"))
        )
        # Capture the tool classes the agent actually used and what the task required.
        tool_classes_used = _used_tool_classes(
            behavior_transcript if behavior_trusted else ""
        )
        required_tool_classes = task.metadata.get("tool_use_requirements", [])
        return TaskResult(
            task_id=task.metadata["id"],
            category=task.metadata["category"],
            status=status,
            score=effective_score,
            passed=effective_score >= 1.0,
            wall_time_seconds=round(time.time() - t0, 3),
            task_quality_tier=task_quality_tier(task, ROOT),
            raw_task_score=raw_score,
            effective_task_score=effective_score,
            behavior_penalty=behavior_penalty,
            passed_raw=raw_score >= 1.0,
            passed_effective=effective_score >= 1.0,
            verification_claimed=verification_claimed,
            verification_sufficient=verification_sufficient,
            tool_calls=ar.tool_calls if ar else 0,
            token_usage=ar.token_usage if ar else None,
            cost_usd=ar.cost_usd if ar else None,
            false_done=false_done,
            timeout=timeout,
            stalled=stalled,
            verification_evidence=evidence + behavior_evidence,
            logs={
                "transcript": ar.transcript[:4000] if ar else "",
                # Keep structured tool provenance alongside the bounded model
                # transcript. Quiet Hermes CLI runs put tool calls in the
                # temporary state DB, so transcript-only diagnostics cannot
                # explain stalled browser/cron trajectories.
                "tool_trace": ar.tool_events if ar else [],
                "telemetry_source": ar.telemetry_source if ar else None,
                "sandbox": _sandbox_metadata(wd),
            },
            tool_classes_used=list(tool_classes_used),
            required_tool_classes=list(required_tool_classes),
            runtime_issues=sorted(runtime_issues),
        )


def _environment_skip_result(task, toolsets: list[str]) -> TaskResult:
    reason = "Hermes CLI toolsets unavailable: " + ", ".join(toolsets)
    return TaskResult(
        task_id=task.metadata["id"],
        category=task.metadata["category"],
        status="environment_skipped",
        score=0.0,
        passed=False,
        wall_time_seconds=0.0,
        task_quality_tier=task_quality_tier(task, ROOT),
        raw_task_score=0.0,
        effective_task_score=0.0,
        environment_skip=True,
        skip_reason=reason,
        verification_evidence=[reason],
        tool_classes_used=[],
        required_tool_classes=list(task.metadata.get("tool_use_requirements", [])),
    )


def run_benchmark(
    agent="hermes",
    suite="hermes-core",
    task_id=None,
    output_dir="results",
    model=None,
    command=None,
    benchmark_version=None,
    provider=None,
    reasoning_effort=None,
    task_root=None,
    jobs: int | str | None = None,
    quantization=None,
    backend=None,
    profile="hermesbench",
    stall_idle_seconds=300.0,
) -> Path:
    provider, model = _split_provider_model(provider, model)
    version_info = resolve_version(benchmark_version)
    if benchmark_version and version_info["suite"] != suite:
        raise ValueError("benchmark version does not match selected suite")
    tasks = discover_tasks(suite, ROOT, task_root)
    if task_id:
        tasks = [t for t in tasks if t.metadata["id"] == task_id]
    if not tasks:
        raise ValueError("no tasks selected")
    if agent == "hermes":
        from .adapters.hermes import unsupported_cli_toolsets

        unsupported = {
            task.metadata["id"]: unsupported_cli_toolsets(
                task, check_runtime=suite == "hermes-extended"
            )
            for task in tasks
        }
        unsupported = {
            task_id: names for task_id, names in unsupported.items() if names
        }
        runnable_tasks = [task for task in tasks if task.metadata["id"] not in unsupported]
        skipped_results = {
            task_id: _environment_skip_result(
                next(task for task in tasks if task.metadata["id"] == task_id), names
            )
            for task_id, names in unsupported.items()
        }
    else:
        runnable_tasks = tasks
        skipped_results = {}
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    started = datetime.now(timezone.utc).isoformat()
    run_t0 = time.perf_counter()
    max_workers = _resolve_jobs(jobs, len(runnable_tasks))
    if max_workers == 1:
        results = [
            _run_one_task(
                task, agent, model, command, provider, reasoning_effort, profile,
                stall_idle_seconds,
            )
            for task in runnable_tasks
        ]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            results = list(
                pool.map(
                    lambda task: _run_one_task(
                        task, agent, model, command, provider, reasoning_effort, profile,
                        stall_idle_seconds,
                    ),
                    runnable_tasks,
                )
            )
    results_by_id = {result.task_id: result for result in results}
    results = [
        results_by_id[task.metadata["id"]]
        if task.metadata["id"] in results_by_id
        else skipped_results[task.metadata["id"]]
        for task in tasks
    ]
    # Preserve a positive runtime for completed runs even when a very fast
    # task rounds below the millisecond display precision used in metadata.
    run_wall_time = max(round(time.perf_counter() - run_t0, 3), 0.001)
    completed = datetime.now(timezone.utc).isoformat()

    # Build structured run-ledger metadata.
    run_meta = _collect_run_metadata(
        provider=provider,
        model=model,
        reasoning_effort=reasoning_effort,
        quantization=quantization,
        backend=backend,
        profile=profile,
        benchmark_version=version_info["version"],
        jobs=max_workers,
        run_wall_time_seconds=run_wall_time,
        command=command,
    )

    # Merge into the flat metadata dict (stays within MAX_RESULT_METADATA_KEYS=20).
    # Start with existing runner-specific fields.
    flat: dict[str, Any] = {
        "task_count": len(results),
        "public_output_redacts_hidden_checks": True,
        "task_root": str(task_root) if task_root else None,
    }
    # Add all non-None values from the structured ledger.
    flat.update(run_meta.to_metadata_dict())

    run = RunResult(
        "hermesbench.result.v1",
        uuid.uuid4().hex[:12],
        suite,
        agent,
        model,
        started,
        completed,
        results,
        flat,
    )
    path = out / f"hermesbench-{run.run_id}.json"
    path.write_text(json.dumps(run.to_jsonable(), indent=2))
    return path
