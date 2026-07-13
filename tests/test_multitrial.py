from __future__ import annotations

import json
from pathlib import Path

import pytest

from hermesbench.multitrial import aggregate_trials


def _run(path: Path, run_id: str, scores: tuple[float, float], *, model: str = "m") -> Path:
    payload = {
        "schema_version": "hermesbench.result.v1",
        "run_id": run_id,
        "suite": "hermes-core-private",
        "agent": "hermes",
        "model": model,
        "started_at": "2026-07-13T00:00:00+00:00",
        "completed_at": "2026-07-13T00:01:00+00:00",
        "metadata": {
            "provider": "test",
            "benchmark_version": "hermes-core-v0.2-private",
            "private_pack_id": "pack-sha256:abc",
            "git_commit": "deadbee",
            "git_dirty": False,
        },
        "results": [
            {
                "task_id": f"private-{i}",
                "category": "natural-tool-use",
                "status": "passed" if score == 1 else "failed",
                "score": score,
                "passed": score == 1,
                "wall_time_seconds": 1.0,
                "required_tool_classes": ["file"],
                "tool_classes_used": ["file"] if score == 1 else [],
                "runtime_issues": [],
            }
            for i, score in enumerate(scores, 1)
        ],
    }
    path.write_text(json.dumps(payload))
    return path


def test_aggregate_trials_reports_stability_and_per_task_rates(tmp_path):
    paths = [
        _run(tmp_path / "a.json", "a", (1.0, 0.0)),
        _run(tmp_path / "b.json", "b", (1.0, 1.0)),
        _run(tmp_path / "c.json", "c", (1.0, 1.0)),
    ]

    result = aggregate_trials(paths)

    assert result["schema_version"] == "hermesbench.trials.v1"
    assert result["trial_count"] == 3
    assert result["score_mean"] == pytest.approx(5 / 6)
    assert result["score_min"] == 0.5
    assert result["score_max"] == 1.0
    assert result["perfect_trial_rate"] == pytest.approx(2 / 3)
    assert result["capability_pass_rate"] == pytest.approx(2 / 3)
    assert result["task_stability"]["private-1"]["pass_rate"] == 1.0
    assert result["task_stability"]["private-2"]["pass_rate"] == pytest.approx(2 / 3)
    assert result["private_pack_id"] == "pack-sha256:abc"
    assert result["runner_commit"] == "deadbee"
    assert result["trial_run_ids"] == ["a", "b", "c"]


def test_aggregate_trials_rejects_mixed_identity(tmp_path):
    a = _run(tmp_path / "a.json", "a", (1.0, 1.0))
    b = _run(tmp_path / "b.json", "b", (1.0, 1.0), model="other")

    with pytest.raises(ValueError, match="model"):
        aggregate_trials([a, b])
