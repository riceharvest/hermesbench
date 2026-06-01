import json, subprocess, sys
from pathlib import Path
from hermesbench.tasks import discover_tasks, parse_task_markdown, validate_tasks, task_quality_tier
from hermesbench.runner import run_benchmark
from hermesbench.scoring import aggregate
from hermesbench.schemas import validate_result_schema

def test_task_suite_has_30_valid_public_tasks():
    tasks=discover_tasks('public-dev')
    assert len(tasks) >= 30
    assert not validate_tasks()

def test_public_dev_tasks_are_not_marker_only():
    tasks=discover_tasks('public-dev')
    shallow=[]
    for task in tasks:
        prompt=task.prompt.lower(); rubric=task.scoring_rubric.lower()
        fixture_dir=Path('fixtures')/task.metadata['id']
        fixture_files=[p for p in fixture_dir.rglob('*') if p.is_file() and p.name.lower()!='readme.txt'] if fixture_dir.exists() else []
        has_fixture=bool(fixture_files) or task.metadata.get('no_fixture_required') is True
        quality_notes=str(task.metadata.get('quality_notes',''))
        checks_text=' '.join(str(c) for c in task.deterministic_checks).lower()
        facts=sum(1 for token in ['fixture_version','expected_total','record_count','incident_id','policy_code','checksum','dataset_id','owner','deadline'] if token in prompt or token in rubric or token in checks_text)
        generic_marker=all(a.endswith('completion.txt') or a.endswith('marker.txt') for a in task.expected_artifacts)
        scoring_words=[task.metadata['category'].replace('-',' '), 'json', 'evidence', 'verify', 'deterministic']
        if (not has_fixture or facts < 2 or generic_marker or len(task.metadata.get('contamination_notes','')) < 40 or not any(w in rubric for w in scoring_words) or len(quality_notes) < 30):
            shallow.append(task.metadata['id'])
    assert not shallow

def test_quality_lint_flags_shallow_marker_only_tasks(tmp_path):
    tasks_dir=tmp_path/'tasks'; suite=tasks_dir/'public-dev'; suite.mkdir(parents=True)
    md='''---\nid: shallow\ntitle: Shallow\ncategory: cat\nwave: 1\nvisibility: public\ncreated_at: 2026-01-01\nfreshness_window: static\nexpected_human_minutes: 1\ndifficulty: easy\nrequired_toolsets: []\ngrading_type: deterministic\ntimeout_seconds: 10\ncontamination_notes: note long enough to be meaningful\nsafety_notes: none\n---\n## Prompt\nDo it.\n## Expected artifacts\n- done.txt\n## Deterministic checks\n- artifact_exists: done.txt\n'''
    (suite/'shallow.md').write_text(md)
    (tasks_dir/'manifest.yaml').write_text('suite: public-dev\ntasks:\n- id: shallow\n  path: public-dev/shallow.md\n  category: cat\n  visibility: public\n')
    structural=validate_tasks(task_root=tasks_dir)
    quality=validate_tasks(task_root=tasks_dir, quality_only=True)
    assert structural == []
    assert any('has 1 deterministic checks' in e for e in quality)
    assert any('marker-only' in e for e in quality)
    assert any('no semantic validation' in e for e in quality)
    assert task_quality_tier(discover_tasks('public-dev', task_root=tasks_dir)[0], tmp_path) == 'needs-review'

    from hermesbench.graders.deterministic import run_checks
    (tmp_path/'artifacts').mkdir()
    (tmp_path/'artifacts/report.json').write_text('{"ok": true, "count": 3, "name": "alpha"}')
    checks=[
        {'type':'json_field','path':'artifacts/report.json','expr':'ok=true'},
        {'type':'json_field','path':'artifacts/report.json','expr':'count=3'},
        {'type':'command_passes','command':'test -f artifacts/report.json'},
    ]
    score,evidence=run_checks(tmp_path, checks)
    assert score == 1.0
    assert all('PASS' in e for e in evidence)

def test_task_markdown_parser_extracts_checks():
    task=discover_tasks('public-dev')[0]
    parsed=parse_task_markdown(task.path)
    assert parsed.metadata['id'].startswith('hb-dev-')
    assert parsed.deterministic_checks

def test_mock_adapter_run_and_score(tmp_path):
    result=run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path)
    data=json.loads(Path(result).read_text())
    validate_result_schema(data)
    score=aggregate(result)
    assert score['overall_score'] == 1.0
    assert score['pass_at_1'] == 1.0

def test_provider_model_reasoning_metadata(tmp_path):
    result=run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path, model='openaicodex/gpt-5.5', reasoning_effort='low')
    data=json.loads(Path(result).read_text())
    score=aggregate(result)
    assert data['model'] == 'gpt-5.5'
    assert data['metadata']['provider'] == 'openai-codex'
    assert data['metadata']['reasoning_effort'] == 'low'
    assert score['provider'] == 'openai-codex'
    assert score['reasoning_effort'] == 'low'

def test_cli_smoke_validate_and_export(monkeypatch):
    import os
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path.cwd() / 'src')
    assert subprocess.run([sys.executable,'-m','hermesbench.cli','validate-tasks'], text=True, capture_output=True, env=env).returncode == 0
    out=subprocess.run([sys.executable,'-m','hermesbench.cli','export','--format','jsonl'], text=True, capture_output=True, env=env)
    assert out.returncode == 0
    assert 'hb-dev-001' in out.stdout
