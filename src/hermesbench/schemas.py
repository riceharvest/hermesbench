from __future__ import annotations

import hmac
import math
from dataclasses import dataclass, asdict, field
from typing import Any

RESULT_SCHEMA_VERSION = "hermesbench.result.v1"

REQUIRED_TASK_FIELDS = {"id","title","category","wave","visibility","created_at","freshness_window","expected_human_minutes","difficulty","required_toolsets","grading_type","timeout_seconds","contamination_notes","safety_notes"}
GRADING_TYPES = {"deterministic","artifact","test","judge","hybrid"}
QUALITY_TIERS = {"gold", "silver", "bronze", "experimental", "needs-review"}
NATURAL_TOOL_CLASSES = {
    "file", "terminal", "web", "browser", "browser_cdp", "code_execution", "vision", "image_gen",
    "video", "video_gen", "tts", "memory", "todo", "skills", "session_search", "semantic_search",
    "delegation", "clarify", "cronjob", "computer_use", "homeassistant", "kanban", "project",
    "discord", "discord_admin", "x_search", "yuanbao", "spotify", "feishu", "messaging",
    "stt", "obsidian", "github", "docker", "notion", "linear", "maps", "himalaya", "openhue",
}

# Hard limits matching the JS Vercel contract.
MAX_RESULT_TASKS = 200
MAX_RESULT_METADATA_KEYS = 20

@dataclass
class Task:
    metadata: dict[str, Any]
    prompt: str
    setup: str
    expected_artifacts: list[str]
    scoring_rubric: str
    deterministic_checks: list[dict[str, Any]]
    hidden_checks: list[dict[str, Any]]
    cleanup: str
    path: str

@dataclass
class TaskResult:
    task_id: str
    category: str
    status: str
    score: float
    passed: bool
    wall_time_seconds: float
    task_quality_tier: str = "unknown"
    raw_task_score: float | None = None
    effective_task_score: float | None = None
    behavior_penalty: float = 0.0
    passed_raw: bool | None = None
    passed_effective: bool | None = None
    verification_claimed: bool = False
    verification_sufficient: bool = False
    tool_calls: int = 0
    token_usage: dict[str, int | float] | None = None
    cost_usd: float | None = None
    false_done: bool = False
    timeout: bool = False
    environment_skip: bool = False
    skip_reason: str | None = None
    verification_evidence: list[str] | None = None
    logs: dict[str, Any] | None = None
    tool_classes_used: list[str] | None = None
    required_tool_classes: list[str] | None = None

@dataclass
class RunLedgerMetadata:
    """Structured run-level metadata for model identity, runtime, hardware,
    provenance, and measurement sources.

    All fields default to ``None`` — the runner populates what it can safely
    discover.  No private paths, secrets, or API keys are recorded.
    The ``metadata_available`` sub-dict flags which categories of metadata
    were actually populated (so consumers can distinguish "ran but got None"
    from "was never instrumented").
    """

    # ── Model identity ─────────────────────────────────────────────────
    provider: str | None = None
    """LLM provider (e.g. ``"openai"``, ``"deepseek"``)."""
    model: str | None = None
    """Model identifier (e.g. ``"deepseek-chat"``)."""
    reasoning_effort: str | None = None
    """Reasoning effort setting (``"low"``, ``"high"``, etc.)."""
    quantization: str | None = None
    """Quantization level (e.g. ``"Q4_K_M"``), or ``None`` for unquantized."""
    backend: str | None = None
    """Serving / inference backend (e.g. ``"llama.cpp"``, ``"sglang"``)."""

    # ── Runner / runtime ───────────────────────────────────────────────
    profile: str | None = None
    """Hermes agent profile name."""
    benchmark_version: str | None = None
    """Resolved benchmark version string (e.g. ``"hermes-core-v0.1"``)."""
    jobs: int | None = None
    """Number of parallel workers used."""
    run_wall_time_seconds: float | None = None
    """Monotonic wall-clock time for the entire run, in seconds."""
    engine_version: str | None = None
    """Adapter / CLI engine version (e.g. hermes CLI version, openai-codex version)."""
    hermes_version: str | None = None
    """Hermes Agent version if available."""

    # ── Generation / provenance ────────────────────────────────────────
    git_commit: str | None = None
    """Short git commit hash of the HermesBench checkout, or ``None``."""
    command: str | None = None
    """Invocation command (secrets scrubbed)."""
    config_summary: dict[str, Any] | None = None
    """Non-secret configuration summary."""

    # ── Platform / hardware ────────────────────────────────────────────
    os_platform: str | None = None
    """OS description (``platform.platform()``)."""
    python_version: str | None = None
    """Python version string."""
    cpu_info: str | None = None
    """CPU model / count if safely discoverable."""
    gpu_info: str | None = None
    """GPU model / count if safely discoverable (no drivers invoked)."""

    # ── Measurement-source availability markers ────────────────────────
    metadata_available: dict[str, bool] = field(default_factory=dict)
    """Flags which metadata categories were populated.

    Keys are dotted category paths (e.g. ``"model_identity"``,
    ``"provenance"``, ``"hardware"``).  Consumers can use this to
    distinguish ``None``-from-unpopulated vs ``None``-from-unavailable.
    """

    def to_metadata_dict(self) -> dict[str, Any]:
        """Flatten to a single-level dict suitable for ``RunResult.metadata``.

        Only non-None values are included (to conserve the 20-key limit).
        The ``metadata_available`` marker is always included.
        Compound fields (``config_summary``, ``metadata_available``) are
        kept as sub-dicts.
        """
        d: dict[str, Any] = {}
        for key in (
            "provider", "model", "reasoning_effort", "quantization", "backend",
            "profile", "benchmark_version", "jobs", "run_wall_time_seconds",
            "engine_version", "hermes_version",
            "git_commit", "command", "config_summary",
            "os_platform", "python_version", "cpu_info", "gpu_info",
        ):
            val = getattr(self, key, None)
            if val is not None:
                d[key] = val
        if self.metadata_available:
            d["metadata_available"] = self.metadata_available
        else:
            # Always include the marker so consumers know it's intentional.
            d["metadata_available"] = {}
        return d

    @classmethod
    def from_metadata_dict(cls, d: dict[str, Any]) -> RunLedgerMetadata:
        """Inverse of ``to_metadata_dict``."""
        return cls(
            provider=d.get("provider"),
            model=d.get("model"),
            reasoning_effort=d.get("reasoning_effort"),
            quantization=d.get("quantization"),
            backend=d.get("backend"),
            profile=d.get("profile"),
            benchmark_version=d.get("benchmark_version"),
            jobs=d.get("jobs"),
            run_wall_time_seconds=d.get("run_wall_time_seconds"),
            engine_version=d.get("engine_version"),
            hermes_version=d.get("hermes_version"),
            git_commit=d.get("git_commit"),
            command=d.get("command"),
            config_summary=d.get("config_summary"),
            os_platform=d.get("os_platform"),
            python_version=d.get("python_version"),
            cpu_info=d.get("cpu_info"),
            gpu_info=d.get("gpu_info"),
            metadata_available=d.get("metadata_available", {}),
        )


@dataclass
class RunResult:
    schema_version: str
    run_id: str
    suite: str
    agent: str
    model: str | None
    started_at: str
    completed_at: str
    results: list[TaskResult]
    metadata: dict[str, Any]

    def to_jsonable(self):
        d=asdict(self); d['results']=[asdict(r) for r in self.results]; return d

def validate_result_schema(data: dict[str, Any]) -> None:
    """Validate a result dict against the Vercel-contract schema.

    Raises ValueError on any violation. Mirrors the JS ``validateResultShape``
    plus tight field-type, score-bounds, and hard-limit checks.
    """
    if not isinstance(data, dict):
        raise ValueError("result must be a dict")
    if data.get("schema_version") != RESULT_SCHEMA_VERSION:
        raise ValueError(
            f"invalid schema_version: expected {RESULT_SCHEMA_VERSION!r}, "
            f"got {data.get('schema_version')!r}"
        )
    for field in ("run_id", "agent", "suite"):
        val = data.get(field)
        if not isinstance(val, str) or not val:
            raise ValueError(f"missing or non-empty-string result field: {field}")
    started = data.get("started_at")
    completed = data.get("completed_at")
    if not isinstance(started, str) or not started:
        raise ValueError("missing or non-empty-string result field: started_at")
    if not isinstance(completed, str) or not completed:
        raise ValueError("missing or non-empty-string result field: completed_at")
    results = data.get("results")
    if not isinstance(results, list):
        raise ValueError("results must be a list")
    if len(results) > MAX_RESULT_TASKS:
        raise ValueError(
            f"task count {len(results)} exceeds maximum {MAX_RESULT_TASKS}"
        )
    metadata = data.get("metadata")
    if not isinstance(metadata, dict) or metadata is None:
        raise ValueError("metadata must be a dict")
    if len(metadata) > MAX_RESULT_METADATA_KEYS:
        raise ValueError(
            f"metadata key count {len(metadata)} exceeds maximum {MAX_RESULT_METADATA_KEYS}"
        )
    for r in results:
        if not isinstance(r, dict):
            raise ValueError("each task result must be a dict")
        for field in ("task_id", "category", "status"):
            val = r.get(field)
            if not isinstance(val, str) or not val:
                raise ValueError(f"missing or non-empty-string task result field: {field}")
        score = r.get("score")
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            raise ValueError("task result score must be a number")
        if math.isnan(score):
            raise ValueError(f"task result score is NaN")
        if score < 0.0 or score > 1.0:
            raise ValueError(f"task result score {score!r} out of range [0, 1]")
        passed = r.get("passed")
        if not isinstance(passed, bool):
            raise ValueError("task result passed must be a boolean")
        wt = r.get("wall_time_seconds")
        if isinstance(wt, bool) or not isinstance(wt, (int, float)):
            raise ValueError("task result wall_time_seconds must be a number")
        if math.isnan(wt):
            raise ValueError(f"task result wall_time_seconds is NaN")
        if wt < 0:
            raise ValueError(f"task result wall_time_seconds ({wt}) must be non-negative")


# ── Explicit public allowlists (identical in JS tokenFromRequest counterpart) ──
# Fields allowed in public-safe result payloads: metadata-level.
PUBLIC_METADATA_KEYS: set[str] = {
    "sanitized", "official",
    # Run-ledger metadata (non-secret identity, runtime, provenance, hardware)
    "provider", "model", "reasoning_effort", "quantization", "backend",
    "profile", "benchmark_version", "jobs", "run_wall_time_seconds",
    "engine_version", "hermes_version", "git_commit", "command",
    "config_summary",
    "os_platform", "python_version", "cpu_info", "gpu_info",
    "metadata_available",
    # Legacy fields kept for backward compatibility
    "agent_version", "runner", "environment", "ci_run", "suite",
}
# Fields allowed per-task in public-safe result payloads.
PUBLIC_TASK_KEYS: set[str] = {
    "task_id", "category", "status", "score", "passed",
    "wall_time_seconds", "tool_calls", "token_usage",
    "checks", "timeout", "false_done", "plumbing_audit", "source",
}
# Fields allowed in public leaderboard score entries.
PUBLIC_SCORE_FIELDS: set[str] = {
    "run_id", "agent", "provider", "model", "suite",
    "overall_score", "pass_at_1", "task_count", "official", "submitted_at",
}
# Sensitive log/transcript keys stripped from sanitized output.
SENSITIVE_LOG_KEYS: set[str] = {"transcript", "stdout", "stderr", "logs", "messages"}


def extract_token_from_request(
    headers: dict[str, str] | None,
) -> str | None:
    """Extract a submission token from request headers **only**.

    Header-only contract (matching the JS ``tokenFromRequest`` after
    the body-token fallback was removed):

    1. ``X-Hermesbench-Submission-Token`` header
    2. ``Authorization: Bearer *** header

    Returns ``None`` when no token is found.  ``submission_token`` in the
    request body is **never** accepted — submit via header only.
    """
    headers = headers or {}
    # Header token (case-insensitive key lookup)
    for hk, hv in headers.items():
        if hk.lower() == "x-hermesbench-submission-token":
            if hv and isinstance(hv, str):
                return hv
    # Authorization: Bearer ***
    for hk, hv in headers.items():
        if hk.lower() == "authorization":
            if isinstance(hv, str) and hv.lower().startswith("bearer "):
                return hv[7:].strip()
    return None


def timing_safe_compare(a: str | None, b: str | None) -> bool:
    """Constant-time string comparison, matching JS ``timingSafeEqual``."""
    left = (a or "").encode("utf-8")
    right = (b or "").encode("utf-8")
    return hmac.compare_digest(left, right) and bool(left)  # also reject empty-vs-empty