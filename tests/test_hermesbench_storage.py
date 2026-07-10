import json
from pathlib import Path

import pytest

from hermesbench.runner import run_benchmark
from hermesbench.storage import SQLiteSubmissionStore, create_sqlite_store


NATURAL_TASK = "htu-dev-001-file-and-terminal-self-serve"


def _payload(tmp_path, run_id="run-1", score=1.0, official=False):
    payload = {
        "schema_version": "hermesbench.result.v1",
        "run_id": run_id,
        "suite": "natural-tools-dev",
        "agent": "hermes",
        "model": "test-model",
        "started_at": "2026-07-10T00:00:00Z",
        "completed_at": "2026-07-10T00:01:00Z",
        "metadata": {"official": official},
        "submission_token": "secret",
        "results": [
            {
                "task_id": "t1",
                "category": "natural-tool-use",
                "status": "passed" if score >= 1.0 else "failed",
                "score": score,
                "passed": score >= 1.0,
                "wall_time_seconds": 1.0,
            }
        ],
    }
    return payload


def test_sqlite_store_inserts_submission_and_strips_token(tmp_path):
    store = create_sqlite_store(tmp_path / "submissions.db")
    store.append(_payload(tmp_path))
    rows = store.read_all()
    assert rows[0]["run_id"] == "run-1"
    assert "submission_token" not in rows[0]


def test_sqlite_store_rejects_duplicate_run_id(tmp_path):
    store = SQLiteSubmissionStore(tmp_path / "submissions.db")
    payload = _payload(tmp_path)
    store.append(payload)
    with pytest.raises(ValueError, match="duplicate run_id"):
        store.append(payload)


def test_sqlite_leaderboard_sorted_and_filterable(tmp_path):
    store = create_sqlite_store(tmp_path / "submissions.db")
    store.append(_payload(tmp_path, run_id="low", score=0.25, official=False))
    store.append(_payload(tmp_path, run_id="high", score=1.0, official=True))
    assert [r["run_id"] for r in store.leaderboard()] == ["high", "low"]
    assert [r["run_id"] for r in store.leaderboard(official=True)] == ["high"]
    assert [r["run_id"] for r in store.leaderboard(official=False)] == ["low"]
