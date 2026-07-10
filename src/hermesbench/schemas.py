from __future__ import annotations

import hmac
from dataclasses import dataclass, asdict
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
    verification_evidence: list[str] | None = None
    logs: dict[str, Any] | None = None
    tool_classes_used: list[str] | None = None
    required_tool_classes: list[str] | None = None

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
        if not isinstance(score, (int, float)):
            raise ValueError("task result score must be a number")
        if score < 0.0 or score > 1.0:
            raise ValueError(f"task result score {score!r} out of range [0, 1]")
        passed = r.get("passed")
        if not isinstance(passed, bool):
            raise ValueError("task result passed must be a boolean")
        wt = r.get("wall_time_seconds")
        if not isinstance(wt, (int, float)):
            raise ValueError("task result wall_time_seconds must be a number")


# ── Explicit public allowlists (identical in JS tokenFromRequest counterpart) ──
# Fields allowed in public-safe result payloads: metadata-level.
PUBLIC_METADATA_KEYS: set[str] = {
    "sanitized", "official", "reasoning_effort", "agent_version", "runner",
    "environment", "ci_run", "provider", "model", "suite",
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