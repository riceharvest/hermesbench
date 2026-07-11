import json, subprocess, sys
from pathlib import Path
from hermesbench.versions import resolve_version
from hermesbench.tasks import (
    discover_tasks,
    parse_task_markdown,
    validate_tasks,
    task_quality_tier,
)
from hermesbench.runner import run_benchmark
from hermesbench.scoring import aggregate
from hermesbench.schemas import RunResult, TaskResult, validate_result_schema


def test_hermes_core_suite_has_shipped_tasks():
    tasks = discover_tasks("hermes-core")
    expected = resolve_version("hermes-core-v0.1")["task_count"]
    assert len(tasks) == expected
    assert all(t.metadata.get("tool_use_requirements") for t in tasks)
    assert not validate_tasks()


def test_hermes_core_tasks_are_open_ended():
    tasks = discover_tasks("hermes-core")
    for task in tasks:
        assert task.metadata.get("grading_type") in ("deterministic", "behavior")
        assert task.metadata.get("tool_use_requirements")


def test_quality_lint_flags_shallow_marker_only_tasks(tmp_path):
    tasks_dir = tmp_path / "tasks"
    suite = tasks_dir / "hermes-core"
    suite.mkdir(parents=True)
    md = """---
id: shallow
title: Shallow
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
contamination_notes: note long enough to be meaningful
safety_notes: none
---
## Prompt
Do it.
## Expected artifacts
- done.txt
## Deterministic checks
- artifact_exists: done.txt
"""
    (suite / "shallow.md").write_text(md)
    (tasks_dir / "manifest.yaml").write_text(
        "suites:\n"
        "  hermes-core:\n"
        "    version: test\n"
        "    tasks:\n"
        "    - id: shallow\n"
        "      path: hermes-core/shallow.md\n"
        "      category: natural-tool-use\n"
        "      visibility: public\n"
    )
    structural = validate_tasks(task_root=tasks_dir)
    quality = validate_tasks(task_root=tasks_dir, quality_only=True)
    assert structural == []
    assert any("has 1 deterministic checks" in e for e in quality)
    assert any("marker-only" in e for e in quality)
    assert any("no semantic validation" in e for e in quality)
    assert (
        task_quality_tier(
            discover_tasks("hermes-core", task_root=tasks_dir)[0], tmp_path
        )
        == "needs-review"
    )

    from hermesbench.graders.deterministic import run_checks

    (tmp_path / "artifacts").mkdir()
    (tmp_path / "artifacts/report.json").write_text(
        '{"ok": true, "count": 3, "name": "alpha"}'
    )
    checks = [
        {"type": "json_field", "path": "artifacts/report.json", "expr": "ok=true"},
        {"type": "json_field", "path": "artifacts/report.json", "expr": "count=3"},
        {"type": "command_passes", "command": "test -f artifacts/report.json"},
    ]
    score, evidence = run_checks(tmp_path, checks)
    assert score == 1.0
    assert all("PASS" in e for e in evidence)


def test_task_markdown_parser_extracts_checks():
    task = discover_tasks("hermes-core")[0]
    parsed = parse_task_markdown(task.path)
    assert parsed.metadata["id"].startswith("htu-dev-")
    assert parsed.deterministic_checks


def test_hermes_run_marks_unavailable_cli_toolsets_as_environment_skip(tmp_path):
    result = run_benchmark(
        agent="hermes",
        suite="hermes-extended",
        task_id="htu-dev-025-semantic-search",
        output_dir=tmp_path,
    )
    payload = json.loads(result.read_text())
    assert payload["results"][0]["status"] == "environment_skipped"
    assert payload["results"][0]["environment_skip"] is True


def test_hermes_runner_rejects_unknown_toolsets_before_adapter_launch(
    tmp_path, monkeypatch
):
    import pytest
    import hermesbench.runner as runner
    from types import SimpleNamespace

    task = SimpleNamespace(
        metadata={"id": "unknown-toolset", "required_toolsets": ["imaginary_toolset"]}
    )
    monkeypatch.setattr(runner, "discover_tasks", lambda *args, **kwargs: [task])
    monkeypatch.setattr(
        runner,
        "get_adapter",
        lambda *args, **kwargs: pytest.fail("adapter must not launch"),
    )

    with pytest.raises(
        ValueError, match="Unknown task-requested toolsets.*imaginary_toolset"
    ):
        runner.run_benchmark(
            agent="hermes", suite="hermes-core", output_dir=tmp_path
        )


def test_no_mock_cli_choice():
    import subprocess, sys, os
    from pathlib import Path

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    result = subprocess.run(
        [sys.executable, "-m", "hermesbench.cli", "run", "--help"],
        text=True,
        capture_output=True,
        env=env,
    )
    assert result.returncode == 0
    assert "mock" not in result.stdout, "mock adapter must not appear in CLI choices"


def test_no_mock_adapter_import():
    import importlib

    try:
        importlib.import_module("hermesbench.adapters.mock")
        assert False, "mock adapter module must not exist"
    except ModuleNotFoundError:
        pass


def test_no_mock_in_get_adapter():
    from hermesbench.adapters import get_adapter

    try:
        get_adapter("mock")
        assert False, "get_adapter must reject mock"
    except ValueError:
        pass


def test_provider_model_reasoning_metadata(tmp_path):
    tr = TaskResult(
        task_id="test",
        category="natural-tool-use",
        status="passed",
        score=1.0,
        passed=True,
        wall_time_seconds=1.0,
    )
    result = RunResult(
        schema_version="hermesbench.result.v1",
        run_id="test",
        suite="core-cli",
        agent="hermes",
        model="gpt-5.5",
        started_at="s",
        completed_at="c",
        results=[tr],
        metadata={
            "profile": "hermesbench",
            "provider": "openai-codex",
            "reasoning_effort": "low",
        },
    )
    out = tmp_path / "result.json"
    out.write_text(json.dumps(result.to_jsonable()))
    data = json.loads(out.read_text())
    assert data["model"] == "gpt-5.5"
    assert data["metadata"]["profile"] == "hermesbench"
    assert data["metadata"]["provider"] == "openai-codex"
    assert data["metadata"]["reasoning_effort"] == "low"
    score = aggregate(out)
    assert score["provider"] == "openai-codex"
    assert score["reasoning_effort"] == "low"


def test_cli_smoke_validate_and_export(monkeypatch):
    import os

    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd() / "src")
    assert (
        subprocess.run(
            [sys.executable, "-m", "hermesbench.cli", "validate-tasks"],
            text=True,
            capture_output=True,
            env=env,
        ).returncode
        == 0
    )
    out = subprocess.run(
        [sys.executable, "-m", "hermesbench.cli", "export", "--format", "jsonl"],
        text=True,
        capture_output=True,
        env=env,
    )
    assert out.returncode == 0
    assert "htu-dev-001" in out.stdout


# ── Tool-class coverage contract ───────────────────────────────────────────
#
# Intentionally uncovered tool classes — when a new canonical class is added
# to NATURAL_TOOL_CLASSES but no task exercises it yet, add it here temporarily.
# Remove the entry once a covering task exists.  This lets the benchmark evolve
# (you can declare a class canonical before shipping a task for it) while still
# detecting accidental coverage loss (removing a task without updating the gap).
_COVERAGE_GAPS: set[str] = set()


def test_tool_classes_are_valid_and_covered():
    """Validate the tool-class contract:
      1. Every task references only known canonical classes (no typos).
      2. Coverage spans every canonical class except explicit gaps.
      3. Gap entries reference only known canonical classes (no orphans).

    This is stronger than the previous strict-equality check because it also
    validates task requirements one-by-one, while the gap mechanism lets the
    benchmark add canonical classes ahead of having shipping tasks.
    """
    from hermesbench.schemas import NATURAL_TOOL_CLASSES

    tasks = discover_tasks("hermes-core") + discover_tasks("hermes-extended")
    covered: set[str] = set()

    for t in tasks:
        reqs = t.metadata.get("tool_use_requirements") or []
        for r in reqs:
            assert r in NATURAL_TOOL_CLASSES, (
                f"Task {t.metadata['id']} references unknown tool class {r!r}. "
                f"Add to NATURAL_TOOL_CLASSES in schemas.py, or fix the typo."
            )
            covered.add(r)

    # All non-gap canonical classes must be covered
    expected_covered = NATURAL_TOOL_CLASSES - _COVERAGE_GAPS
    missing = expected_covered - covered
    assert not missing, (
        f"Tasks are missing coverage for {len(missing)} expected class(es): "
        f"{sorted(missing)}.  Add a task that covers them, or add to "
        f"_COVERAGE_GAPS in this test if intentionally uncovered."
    )

    # Gap entries must be known canonical classes
    orphan_gaps = _COVERAGE_GAPS - NATURAL_TOOL_CLASSES
    assert not orphan_gaps, (
        f"_COVERAGE_GAPS contains {sorted(orphan_gaps)} which are not in "
        f"NATURAL_TOOL_CLASSES"
    )


def test_behavior_grader_maps_all_tool_classes():
    """Every canonical tool class must have at least one entry in the
    behavior grader's tool-name mapping (_BEHAVIOR_TOOLS), and every
    mapped value must be a known canonical class.

    This is a bidirectional integrity contract:
      - Adding a new canonical class without a behavior grader mapping is
        caught (the grader would silently fail to classify its tools).
      - A typo in the grader's mapping (orphan value) is also caught.
    """
    from hermesbench.graders.behavior import _BEHAVIOR_TOOLS
    from hermesbench.schemas import NATURAL_TOOL_CLASSES

    mapped_classes = set(_BEHAVIOR_TOOLS.values())

    # Every canonical class must have at least one behavior mapping
    unmapped = NATURAL_TOOL_CLASSES - mapped_classes
    assert not unmapped, (
        f"Behavior grader has no tool-name mapping for {sorted(unmapped)}. "
        f"Add entries to _BEHAVIOR_TOOLS in graders/behavior.py."
    )

    # Every mapped class must be a known canonical class
    orphans = mapped_classes - NATURAL_TOOL_CLASSES
    assert not orphans, (
        f"_BEHAVIOR_TOOLS maps to unknown class(es) {sorted(orphans)}. "
        f"Fix values or add them to NATURAL_TOOL_CLASSES in schemas.py."
    )


# ── Regression: contract contract detects violations ──────────────────────


def _get_mod():
    """Return this test module via sys.modules (can't self-import at runtime)."""
    import sys
    return sys.modules[__name__]


def test_coverage_contract_rejects_unknown_tool_class(tmp_path, monkeypatch):
    """If a task references a class not in NATURAL_TOOL_CLASSES the contract
    must reject it — this catches typos and missing canonical registrations."""
    import pytest
    from hermesbench.schemas import NATURAL_TOOL_CLASSES
    from types import SimpleNamespace

    mod = _get_mod()
    bad_task = SimpleNamespace(
        metadata={"id": "bad-typo", "tool_use_requirements": ["typo_class"]}
    )
    monkeypatch.setattr(
        mod, "discover_tasks",
        lambda suite, **kw: [bad_task] if suite == "hermes-core" else [],
    )

    with pytest.raises(AssertionError, match="typo_class"):
        mod.test_tool_classes_are_valid_and_covered()


def test_coverage_contract_rejects_orphan_gap(monkeypatch):
    """A _COVERAGE_GAPS entry that doesn't exist in NATURAL_TOOL_CLASSES must
    be caught — prevents dead gap references."""
    import pytest
    mod = _get_mod()
    mod._COVERAGE_GAPS.add("nonexistent_gap")
    try:
        with pytest.raises(AssertionError, match="nonexistent_gap"):
            mod.test_tool_classes_are_valid_and_covered()
    finally:
        mod._COVERAGE_GAPS.discard("nonexistent_gap")


def test_coverage_contract_rejects_uncovered_class(tmp_path, monkeypatch):
    """If a canonical class has no covering task and is not listed in gaps,
    the contract must report the missing class."""
    import pytest
    mod = _get_mod()

    # Save original gap state so mutations cannot accidentally remove a real
    # pre-existing gap if _COVERAGE_GAPS changes in the future.
    original_gaps = set(mod._COVERAGE_GAPS)
    try:
        mod._COVERAGE_GAPS.discard("vision")  # ensure it's not gapped

        # Patch module-level discover_tasks to strip one class from every task
        original = mod.discover_tasks

        def stripped_discover(suite, **kw):
            tasks = original(suite, **kw)
            for t in tasks:
                reqs = t.metadata.get("tool_use_requirements") or []
                t.metadata["tool_use_requirements"] = [
                    r for r in reqs if r != "vision"
                ]
            return tasks

        monkeypatch.setattr(mod, "discover_tasks", stripped_discover)

        with pytest.raises(AssertionError, match="vision"):
            mod.test_tool_classes_are_valid_and_covered()
    finally:
        mod._COVERAGE_GAPS.clear()
        mod._COVERAGE_GAPS.update(original_gaps)


def test_behavior_grader_rejects_unmapped_class(monkeypatch):
    """A canonical class without any behavior mapping should be caught."""
    import pytest
    from hermesbench.graders import behavior as behavior_mod

    mod = _get_mod()
    original = dict(behavior_mod._BEHAVIOR_TOOLS)
    behavior_mod._BEHAVIOR_TOOLS = {
        k: v for k, v in original.items() if v != "vision"
    }
    try:
        with pytest.raises(AssertionError, match="vision"):
            mod.test_behavior_grader_maps_all_tool_classes()
    finally:
        behavior_mod._BEHAVIOR_TOOLS = original


def test_behavior_grader_rejects_orphan_mapping(monkeypatch):
    """A _BEHAVIOR_TOOLS value that isn't a known canonical class must be
    caught — this catches typos in the grader mapping."""
    import pytest
    from hermesbench.graders import behavior as behavior_mod

    mod = _get_mod()
    original = dict(behavior_mod._BEHAVIOR_TOOLS)
    behavior_mod._BEHAVIOR_TOOLS["_test_orphan_tool"] = "orphan_class"
    try:
        with pytest.raises(AssertionError, match="orphan_class"):
            mod.test_behavior_grader_maps_all_tool_classes()
    finally:
        behavior_mod._BEHAVIOR_TOOLS = original
