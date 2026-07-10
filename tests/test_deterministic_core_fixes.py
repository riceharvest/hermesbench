import json
from pathlib import Path

from hermesbench.graders.deterministic import run_checks
from hermesbench.tasks import discover_tasks, validate_tasks
from hermesbench.schemas import RunResult, TaskResult


def test_deterministic_extended_assertions(tmp_path):
    (tmp_path / "out").mkdir()
    (tmp_path / "out/report.json").write_text(
        json.dumps({"a": {"b": [{"value": 10.01}]}, "name": "alpha"})
    )
    (tmp_path / "out/log.txt").write_text("hello build-123\n")
    checks = [
        {
            "type": "json_field",
            "path": "out/report.json",
            "expr": "a.b[0].value~=10±0.05",
        },
        {"type": "json_field", "path": "out/report.json", "expr": "a.b[0].value>=10"},
        {"type": "artifact_matches", "path": "out/log.txt", "pattern": r"build-\d+"},
        {"type": "artifact_not_contains", "path": "out/log.txt", "needle": "SECRET"},
        {"type": "glob_exists", "pattern": "out/*.txt"},
        {
            "type": "command_contains",
            "command": "printf ok",
            "needle": "ok",
            "timeout_seconds": 1,
        },
        {
            "type": "command_not_contains",
            "command": "printf safe",
            "needle": "SECRET",
            "timeout_seconds": 1,
        },
    ]
    score, evidence = run_checks(tmp_path, checks)
    assert score == 1.0
    assert all("PASS" in e for e in evidence)


def test_manifest_is_authoritative_and_validates_extra(tmp_path):
    tasks_dir = tmp_path / "tasks"
    suite = tasks_dir / "natural-tools-dev"
    suite.mkdir(parents=True)
    md = """---
id: listed
title: Listed
category: natural-tool-use
wave: 1
visibility: public
created_at: 2026-01-01
freshness_window: static
expected_human_minutes: 1
difficulty: easy
required_toolsets: []
grading_type: deterministic
timeout_seconds: 10
contamination_notes: note long enough
safety_notes: none
---
## Prompt
Do it.
## Deterministic checks
- artifact_exists: done.txt
"""
    (suite / "listed.md").write_text(md)
    (suite / "extra.md").write_text(md.replace("id: listed", "id: extra"))
    (tasks_dir / "manifest.yaml").write_text(
        "suites:\n"
        "  natural-tools-dev:\n"
        "    version: test\n"
        "    tasks:\n"
        "    - id: listed\n"
        "      path: natural-tools-dev/listed.md\n"
        "      category: natural-tool-use\n"
        "      visibility: public\n"
    )
    tasks = discover_tasks("natural-tools-dev", task_root=tasks_dir)
    assert [t.metadata["id"] for t in tasks] == ["listed"]
    assert any(
        "extra.md missing from manifest" in e
        for e in validate_tasks(task_root=tasks_dir)
    )


def test_false_done_cannot_pass_capability_probe(monkeypatch, tmp_path):
    from hermesbench.adapters.base import AgentRun
    import hermesbench.runner as runner
    from hermesbench.scoring import aggregate

    class FalseDoneAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            return AgentRun(
                status="completed",
                transcript=(
                    "agent.tool_executor: tool read_file completed (test)\n"
                    "agent.tool_executor: tool terminal completed (test)"
                ),
                tool_calls=2,
                claimed_done=True,
            )

    monkeypatch.setattr(
        runner, "get_adapter", lambda *args, **kwargs: FalseDoneAdapter()
    )
    result = runner.run_benchmark(
        agent="hermes",
        suite="natural-tools-dev",
        task_id="htu-dev-001-file-and-terminal-self-serve",
        output_dir=tmp_path,
    )
    task_result = json.loads(Path(result).read_text())["results"][0]
    assert task_result["raw_task_score"] < 1.0
    assert task_result["false_done"] is True
    assert task_result["effective_task_score"] == 0.0
    assert task_result["passed"] is False
    assert aggregate(result)["capability_pass"] is False


def test_result_exposes_effective_scoring_and_sandbox(tmp_path):
    tr = TaskResult(
        task_id="test",
        category="natural-tool-use",
        status="passed",
        score=1.0,
        passed=True,
        wall_time_seconds=1.0,
        raw_task_score=1.0,
        effective_task_score=1.0,
        behavior_penalty=0.0,
        passed_raw=True,
        passed_effective=True,
        verification_claimed=True,
        verification_sufficient=True,
        logs={"sandbox": {"env_policy": {"mode": "inherited-by-adapter"}}},
    )
    result = RunResult(
        schema_version="hermesbench.result.v1",
        run_id="test",
        suite="core-cli",
        agent="hermes",
        model=None,
        started_at="s",
        completed_at="c",
        results=[tr],
        metadata={},
    )
    data = json.loads(json.dumps(result.to_jsonable()))
    r = data["results"][0]
    for key in [
        "raw_task_score",
        "effective_task_score",
        "behavior_penalty",
        "passed_raw",
        "passed_effective",
        "verification_claimed",
        "verification_sufficient",
    ]:
        assert key in r
    assert r["logs"]["sandbox"]["env_policy"]["mode"] == "inherited-by-adapter"
