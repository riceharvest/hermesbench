from __future__ import annotations
import json
from pathlib import Path

from scripts.generate_website_data import build_data
from hermesbench.submissions import make_submission_payload
from hermesbench.tasks import discover_tasks


def _result(path: Path, run_id="r1", official=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    data={"schema_version":"hermesbench.result.v1","run_id":run_id,"suite":"public-dev","agent":"agent","model":"model","started_at":"s","completed_at":"c","metadata":{"official":official},"results":[{"task_id":"t1","category":"cat","status":"passed","score":1.0,"passed":True,"wall_time_seconds":1,"logs":{"transcript":"secret"}}]}
    path.write_text(json.dumps(data))
    return path


def test_website_data_generated_from_results_and_splits(tmp_path):
    _result(tmp_path/"results/u/hermesbench-u.json", "u", False)
    _result(tmp_path/"results/o/hermesbench-o.json", "o", True)
    lb, latest = build_data(tmp_path/"results", tmp_path/"out")
    data=json.loads(lb.read_text())
    assert data["official"][0]["run_id"] == "o"
    assert data["unofficial"][0]["classification"] == "unofficial"
    assert json.loads(latest.read_text())["run_id"] in {"o","u"}


def test_upload_payload_strips_logs_and_marks_unofficial(tmp_path):
    rp=_result(tmp_path/"hermesbench-r.json", "r", False)
    payload=make_submission_payload(rp)
    assert payload["classification"] == "unofficial"
    assert "logs" not in payload["result"]["results"][0]
    assert payload["github_issue"]["labels"] == ["hermesbench-submission", "unofficial"]


def test_discover_tasks_uses_task_root(tmp_path):
    root=tmp_path/"packs"; suite=root/"fresh"; suite.mkdir(parents=True)
    (root/"manifest.yaml").write_text("tasks:\n- id: hb-private-001\n")
    (suite/"task.md").write_text("""---
id: hb-private-001
title: Private
category: private
wave: fresh
visibility: private
created_at: '2026-06-01'
freshness_window: 30d
expected_human_minutes: 1
difficulty: easy
required_toolsets: []
grading_type: deterministic
timeout_seconds: 10
contamination_notes: none
safety_notes: none
---
## Prompt
Do it.
## Deterministic checks
- artifact_exists: out.txt
## Hidden checks
- maintained privately
""")
    tasks=discover_tasks("fresh", task_root=root)
    assert [t.metadata["id"] for t in tasks] == ["hb-private-001"]
