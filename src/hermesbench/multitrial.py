from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Iterable

from .schemas import validate_result_schema
from .scoring import aggregate

_IDENTITY_FIELDS = ("agent", "model", "suite")
_METADATA_IDENTITY_FIELDS = (
    "provider",
    "reasoning_effort",
    "benchmark_version",
    "private_pack_id",
    "git_commit",
)


def _load(path: str | Path) -> tuple[Path, dict]:
    resolved = Path(path)
    data = json.loads(resolved.read_text())
    validate_result_schema(data)
    return resolved, data


def _require_equal(runs: list[dict], field: str, *, metadata: bool = False):
    values = [
        run.get("metadata", {}).get(field) if metadata else run.get(field)
        for run in runs
    ]
    if any(value != values[0] for value in values[1:]):
        raise ValueError(f"trial identity mismatch for {field}: {values}")
    return values[0]


def aggregate_trials(paths: Iterable[str | Path]) -> dict:
    """Aggregate repeated, identity-equivalent HermesBench runs.

    The aggregate fails closed when model, provider, suite, benchmark version,
    private-pack identity, runner commit, or task set differs between trials.
    """
    loaded = [_load(path) for path in paths]
    if not loaded:
        raise ValueError("at least one trial result is required")
    files, runs = zip(*loaded)
    runs = list(runs)

    identity = {field: _require_equal(runs, field) for field in _IDENTITY_FIELDS}
    metadata_identity = {
        field: _require_equal(runs, field, metadata=True)
        for field in _METADATA_IDENTITY_FIELDS
    }
    task_ids = [result["task_id"] for result in runs[0]["results"]]
    if len(task_ids) != len(set(task_ids)):
        raise ValueError("duplicate task IDs in trial")
    for run in runs[1:]:
        current = [result["task_id"] for result in run["results"]]
        if current != task_ids:
            raise ValueError("trial identity mismatch for ordered task set")

    scores = [aggregate(path) for path in files]
    overall = [float(score["overall_score"]) for score in scores]
    capability = [bool(score["capability_pass"]) for score in scores]
    evaluable = [bool(score["capability_evaluable"]) for score in scores]
    perfect = [score["task_correctness_pass"] and score["capability_pass"] for score in scores]

    task_stability = {}
    for task_id in task_ids:
        task_rows = [
            next(result for result in run["results"] if result["task_id"] == task_id)
            for run in runs
        ]
        task_scores = [float(row.get("effective_task_score", row.get("score", 0)) or 0) for row in task_rows]
        task_stability[task_id] = {
            "trial_count": len(task_rows),
            "pass_count": sum(bool(row.get("passed")) for row in task_rows),
            "pass_rate": sum(bool(row.get("passed")) for row in task_rows) / len(task_rows),
            "score_mean": statistics.mean(task_scores),
            "score_min": min(task_scores),
            "score_max": max(task_scores),
            "environment_skip_count": sum(bool(row.get("environment_skip")) for row in task_rows),
            "runtime_issue_count": sum(bool(row.get("runtime_issues")) for row in task_rows),
        }

    total_costs: list[float | None] = [score.get("total_cost_usd") for score in scores]
    complete_costs = all(cost is not None for cost in total_costs)
    known_costs = [float(cost) for cost in total_costs if cost is not None]
    private_pack_id = metadata_identity["private_pack_id"]
    return {
        "schema_version": "hermesbench.trials.v1",
        **identity,
        "provider": metadata_identity["provider"],
        "reasoning_effort": metadata_identity["reasoning_effort"],
        "benchmark_version": metadata_identity["benchmark_version"],
        "private_pack_id": private_pack_id,
        "private_pack_sha256": (
            private_pack_id.removeprefix("sha256:")
            if isinstance(private_pack_id, str) and private_pack_id.startswith("sha256:")
            else None
        ),
        "runner_commit": metadata_identity["git_commit"],
        "trial_count": len(runs),
        "trial_run_ids": [run["run_id"] for run in runs],
        "task_count": len(task_ids),
        "score_mean": statistics.mean(overall),
        "score_stddev": statistics.stdev(overall) if len(overall) > 1 else 0.0,
        "score_min": min(overall),
        "score_max": max(overall),
        "perfect_trial_count": sum(perfect),
        "perfect_trial_rate": sum(perfect) / len(perfect),
        "capability_pass_count": sum(capability),
        "capability_pass_rate": sum(capability) / len(capability),
        "evaluable_trial_count": sum(evaluable),
        "evaluable_trial_rate": sum(evaluable) / len(evaluable),
        "total_cost_usd": sum(known_costs) if complete_costs else None,
        "cost_telemetry_complete": complete_costs,
        "task_stability": task_stability,
    }


def write_trial_aggregate(paths: Iterable[str | Path], output: str | Path) -> Path:
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(aggregate_trials(paths), indent=2, sort_keys=True) + "\n")
    return output
