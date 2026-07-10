from pathlib import Path

import yaml

from hermesbench.runner import run_benchmark
from hermesbench.tasks import discover_tasks, validate_tasks
from hermesbench.versions import DEFAULT_BENCHMARK_VERSION, resolve_version


def test_core_cli_suite_contains_only_cli_supported_tasks_and_is_default(tmp_path):
    core = discover_tasks("core-cli")
    integrations = discover_tasks("integrations")
    assert {task.metadata["id"] for task in core} == {
        "htu-dev-001-file-and-terminal-self-serve",
        "htu-dev-007-code-execution",
        "htu-dev-013-vision-image",
    }
    assert {task.metadata["id"] for task in core}.isdisjoint(
        {task.metadata["id"] for task in integrations}
    )
    assert resolve_version(DEFAULT_BENCHMARK_VERSION)["suite"] == "core-cli"
    assert len(core) == 3
    assert len(integrations) == 35

    result = run_benchmark(agent="mock", task_id="htu-dev-001-file-and-terminal-self-serve", output_dir=tmp_path)
    assert '"suite": "core-cli"' in result.read_text()


def test_fixture_contract_rejects_missing_declared_input_and_unsafe_artifact_path(tmp_path):
    tasks = tmp_path / "tasks"
    suite = tasks / "core-cli"
    suite.mkdir(parents=True)
    task = suite / "sample.md"
    task.write_text("""---
id: sample
title: Sample
category: local
wave: 1
visibility: public
created_at: 2026-01-01
freshness_window: static
expected_human_minutes: 1
difficulty: easy
required_toolsets: [file]
fixtures: [input/data.txt]
grading_type: deterministic
timeout_seconds: 10
contamination_notes: none
safety_notes: none
---
## Prompt
Do work.
## Expected artifacts
- ../escape.txt
## Deterministic checks
- artifact_exists: /tmp/escape.txt
""")
    (tasks / "manifest.yaml").write_text(yaml.safe_dump({"suites": {"core-cli": {"version": "test", "tasks": [{"id": "sample", "path": "core-cli/sample.md", "category": "local", "visibility": "public"}]}}}))

    findings = validate_tasks(task_root=tasks)
    assert any("declared fixture missing" in finding for finding in findings)
    assert any("unsafe artifact path" in finding for finding in findings)


def test_core_cli_tasks_declare_every_prompt_fixture_and_have_local_files():
    expected_inputs = {
        "htu-dev-001-file-and-terminal-self-serve": ["data/records.txt"],
        "htu-dev-007-code-execution": ["case/numbers.txt"],
        "htu-dev-013-vision-image": ["case/image.png"],
    }
    for task in discover_tasks("core-cli"):
        assert task.metadata.get("fixtures") == expected_inputs[task.metadata["id"]]
    assert not validate_tasks()


def test_legacy_manifest_does_not_discover_tasks_for_an_unknown_suite(tmp_path):
    task = tmp_path / "only.md"
    task.write_text("""---
id: only
title: Only
category: local
wave: 1
visibility: public
created_at: 2026-01-01
freshness_window: static
expected_human_minutes: 1
difficulty: easy
required_toolsets: []
grading_type: deterministic
timeout_seconds: 10
contamination_notes: none
safety_notes: none
---
## Prompt
Do work.
## Deterministic checks
- artifact_exists: done.txt
""")
    (tmp_path / "manifest.yaml").write_text(yaml.safe_dump({"suite": "legacy", "tasks": [{"id": "only", "path": "only.md"}]}))
    assert [t.metadata["id"] for t in discover_tasks("legacy", task_root=tmp_path)] == ["only"]
    assert discover_tasks("unknown", task_root=tmp_path) == []


def test_benchmark_version_task_counts_match_declared_suites():
    assert resolve_version("core-cli-v0.1")["task_count"] == len(discover_tasks("core-cli")) == 3
    assert resolve_version("natural-tools-dev-v0.1")["task_count"] == len(discover_tasks("natural-tools-dev")) == 38


def test_runner_copies_sibling_fixtures_for_custom_task_packs(tmp_path):
    tasks = tmp_path / "tasks"
    suite = tasks / "local"
    suite.mkdir(parents=True)
    (tmp_path / "fixtures" / "fixture-task" / "case").mkdir(parents=True)
    (tmp_path / "fixtures" / "fixture-task" / "case" / "input.txt").write_text("expected")
    (suite / "fixture-task.md").write_text("""---
id: fixture-task
title: Fixture task
category: local
wave: 1
visibility: public
created_at: 2026-01-01
freshness_window: static
expected_human_minutes: 1
difficulty: easy
required_toolsets: [terminal]
fixtures: [case/input.txt]
grading_type: deterministic
timeout_seconds: 10
contamination_notes: none
safety_notes: none
---
## Prompt
Read `case/input.txt` and create `answer.txt`.
## Expected artifacts
- answer.txt
## Deterministic checks
- artifact_contains: answer.txt => expected
""")
    (tasks / "manifest.yaml").write_text(yaml.safe_dump({"suites": {"local": {"tasks": [{"id": "fixture-task", "path": "local/fixture-task.md", "category": "local", "visibility": "public"}]}}}))
    result = run_benchmark(agent="shell", suite="local", task_id="fixture-task", task_root=tasks, output_dir=tmp_path / "results", command="cp case/input.txt answer.txt")
    assert __import__("json").loads(result.read_text())["results"][0]["passed"] is True
