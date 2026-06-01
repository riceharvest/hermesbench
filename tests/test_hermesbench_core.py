import json, subprocess, sys
from pathlib import Path
from hermesbench.tasks import discover_tasks, parse_task_markdown, validate_tasks
from hermesbench.runner import run_benchmark
from hermesbench.scoring import aggregate
from hermesbench.schemas import validate_result_schema

def test_task_suite_has_30_valid_public_tasks():
    tasks=discover_tasks('public-dev')
    assert len(tasks) >= 30
    assert not validate_tasks()

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

def test_cli_smoke_validate_and_export(monkeypatch):
    import os
    env = os.environ.copy()
    env['PYTHONPATH'] = str(Path.cwd() / 'src')
    assert subprocess.run([sys.executable,'-m','hermesbench.cli','validate-tasks'], text=True, capture_output=True, env=env).returncode == 0
    out=subprocess.run([sys.executable,'-m','hermesbench.cli','export','--format','jsonl'], text=True, capture_output=True, env=env)
    assert out.returncode == 0
    assert 'hb-dev-001' in out.stdout
