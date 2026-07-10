import json, subprocess, sys
from pathlib import Path
from hermesbench.tasks import discover_tasks, parse_task_markdown, validate_tasks, task_quality_tier
from hermesbench.runner import run_benchmark
from hermesbench.scoring import aggregate
from hermesbench.schemas import validate_result_schema


def test_task_suite_has_natural_tools_dev_tasks():
    tasks = discover_tasks('natural-tools-dev')
    assert len(tasks) == 38
    assert all(t.metadata.get('tool_use_requirements') for t in tasks)
    assert not validate_tasks()


def test_natural_tools_dev_tasks_are_open_ended():
    tasks = discover_tasks('natural-tools-dev')
    for task in tasks:
        assert task.metadata.get('grading_type') in ('deterministic', 'behavior')
        assert task.metadata.get('tool_use_requirements')


def test_quality_lint_flags_shallow_marker_only_tasks(tmp_path):
    tasks_dir = tmp_path / 'tasks'
    suite = tasks_dir / 'natural-tools-dev'
    suite.mkdir(parents=True)
    md = '''---
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
'''
    (suite / 'shallow.md').write_text(md)
    (tasks_dir / 'manifest.yaml').write_text(
        'suites:\n'
        '  natural-tools-dev:\n'
        '    version: test\n'
        '    tasks:\n'
        '    - id: shallow\n'
        '      path: natural-tools-dev/shallow.md\n'
        '      category: natural-tool-use\n'
        '      visibility: public\n'
    )
    structural = validate_tasks(task_root=tasks_dir)
    quality = validate_tasks(task_root=tasks_dir, quality_only=True)
    assert structural == []
    assert any('has 1 deterministic checks' in e for e in quality)
    assert any('marker-only' in e for e in quality)
    assert any('no semantic validation' in e for e in quality)
    assert task_quality_tier(discover_tasks('natural-tools-dev', task_root=tasks_dir)[0], tmp_path) == 'needs-review'

    from hermesbench.graders.deterministic import run_checks
    (tmp_path / 'artifacts').mkdir()
    (tmp_path / 'artifacts/report.json').write_text('{"ok": true, "count": 3, "name": "alpha"}')
    checks = [
        {'type': 'json_field', 'path': 'artifacts/report.json', 'expr': 'ok=true'},
        {'type': 'json_field', 'path': 'artifacts/report.json', 'expr': 'count=3'},
        {'type': 'command_passes', 'command': 'test -f artifacts/report.json'},
    ]
    score, evidence = run_checks(tmp_path, checks)
    assert score == 1.0
    assert all('PASS' in e for e in evidence)


def test_task_markdown_parser_extracts_checks():
    task = discover_tasks('natural-tools-dev')[0]
    parsed = parse_task_markdown(task.path)
    assert parsed.metadata['id'].startswith('htu-dev-')
    assert parsed.deterministic_checks


def test_hermes_run_rejects_unavailable_cli_toolsets(tmp_path):
    import pytest

    with pytest.raises(ValueError, match='CLI-unavailable toolsets.*semantic_search'):
        run_benchmark(
            agent='hermes', suite='natural-tools-dev',
            task_id='htu-dev-025-semantic-search', output_dir=tmp_path,
        )


def test_hermes_runner_rejects_unknown_toolsets_before_adapter_launch(tmp_path, monkeypatch):
    import pytest
    import hermesbench.runner as runner
    from types import SimpleNamespace

    task = SimpleNamespace(metadata={'id': 'unknown-toolset', 'required_toolsets': ['imaginary_toolset']})
    monkeypatch.setattr(runner, 'discover_tasks', lambda *args, **kwargs: [task])
    monkeypatch.setattr(runner, 'get_adapter', lambda *args, **kwargs: pytest.fail('adapter must not launch'))

    with pytest.raises(ValueError, match='Unknown task-requested toolsets.*imaginary_toolset'):
        runner.run_benchmark(agent='hermes', suite='natural-tools-dev', output_dir=tmp_path)


def test_mock_adapter_run_and_score(tmp_path):
    result = run_benchmark(
        agent='mock',
        suite='natural-tools-dev',
        task_id='htu-dev-001-file-and-terminal-self-serve',
        output_dir=tmp_path,
    )
    data = json.loads(Path(result).read_text())
    validate_result_schema(data)
    score = aggregate(result)
    # The mock adapter produces deterministic artifacts and mock-emits tool
    # telemetry, so behavior grading successfully passes the capability probe.
    assert score['raw_overall_score'] == 1.0
    assert score['capability_pass'] is True
    assert sorted(score['tool_use_behavior']['tool_classes_used']) == ['file', 'terminal']


def test_provider_model_reasoning_metadata(tmp_path):
    result = run_benchmark(
        agent='mock',
        suite='natural-tools-dev',
        task_id='htu-dev-001-file-and-terminal-self-serve',
        output_dir=tmp_path,
        model='openaicodex/gpt-5.5',
        reasoning_effort='low',
    )
    data = json.loads(Path(result).read_text())
    score = aggregate(result)
    assert data['model'] == 'gpt-5.5'
    assert data['metadata']['provider'] == 'openai-codex'
    assert data['metadata']['reasoning_effort'] == 'low'
    assert score['provider'] == 'openai-codex'
    assert score['reasoning_effort'] == 'low'


def test_cli_smoke_validate_and_export(monkeypatch):
    import os
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path.cwd() / 'src')
    assert subprocess.run(
        [sys.executable, '-m', 'hermesbench.cli', 'validate-tasks'],
        text=True, capture_output=True, env=env,
    ).returncode == 0
    out = subprocess.run(
        [sys.executable, '-m', 'hermesbench.cli', 'export', '--format', 'jsonl'],
        text=True, capture_output=True, env=env,
    )
    assert out.returncode == 0
    assert 'htu-dev-001' in out.stdout


def test_natural_tools_dev_covers_all_tool_classes():
    from hermesbench.schemas import NATURAL_TOOL_CLASSES
    tasks = discover_tasks('natural-tools-dev')
    covered = set()
    for t in tasks:
        reqs = t.metadata.get('tool_use_requirements') or []
        for r in reqs:
            covered.add(r)
    assert covered == NATURAL_TOOL_CLASSES


def test_behavior_grader_maps_new_tool_classes():
    from hermesbench.graders.behavior import _BEHAVIOR_TOOLS
    # Check that all canonical classes in NATURAL_TOOL_CLASSES are mapped
    from hermesbench.schemas import NATURAL_TOOL_CLASSES
    mapped_classes = set(_BEHAVIOR_TOOLS.values())
    for cls in NATURAL_TOOL_CLASSES:
        assert cls in mapped_classes
