from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any

REQUIRED_TASK_FIELDS = {"id","title","category","wave","visibility","created_at","freshness_window","expected_human_minutes","difficulty","required_toolsets","grading_type","timeout_seconds","contamination_notes","safety_notes"}
GRADING_TYPES = {"deterministic","artifact","test","judge","hybrid"}

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
    tool_calls: int = 0
    cost_usd: float | None = None
    false_done: bool = False
    timeout: bool = False
    verification_evidence: list[str] | None = None
    logs: dict[str, Any] | None = None

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
    for k in ["schema_version","run_id","suite","agent","started_at","completed_at","results"]:
        if k not in data: raise ValueError(f"missing result field {k}")
    if not isinstance(data["results"], list): raise ValueError("results must be a list")
    for r in data["results"]:
        for k in ["task_id","category","status","score","passed","wall_time_seconds"]:
            if k not in r: raise ValueError(f"missing task result field {k}")
