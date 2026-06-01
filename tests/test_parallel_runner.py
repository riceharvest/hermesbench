import time
from pathlib import Path

from hermesbench.runner import run_benchmark


def _write_task_pack(root: Path, count: int = 2) -> None:
    suite = root / 'public-dev'
    suite.mkdir(parents=True)
    manifest = ['suite: public-dev', 'version: test', 'tasks:']
    for i in range(count):
        task_id = f'parallel-task-{i}'
        manifest.extend([
            f'- id: {task_id}',
            f'  path: public-dev/{task_id}.md',
            '  category: parallel-test',
            '  visibility: public',
        ])
        (suite / f'{task_id}.md').write_text(f'''---
id: {task_id}
title: Parallel task {i}
category: parallel-test
wave: test
visibility: public
created_at: 2026-06-02
freshness_window: test
expected_human_minutes: 1
difficulty: easy
required_toolsets:
- terminal
grading_type: deterministic
timeout_seconds: 5
contamination_notes: test fixture
safety_notes: local only
---

## Prompt
Create the done artifact after the configured sleep.

## Setup
Local test only.

## Expected artifacts
- done.txt

## Scoring rubric
Passes when done.txt exists.

## Deterministic checks
- artifact_exists: done.txt

## Hidden checks
- none

## Cleanup
Delete the isolated workdir.
''')
    (root / 'manifest.yaml').write_text('\n'.join(manifest) + '\n')


def test_run_benchmark_can_execute_tasks_in_parallel(tmp_path):
    task_root = tmp_path / 'tasks'
    _write_task_pack(task_root, count=2)

    started = time.perf_counter()
    result = run_benchmark(
        agent='shell',
        suite='public-dev',
        output_dir=tmp_path / 'results',
        command="python -c 'import time, pathlib; time.sleep(0.45); pathlib.Path(\"done.txt\").write_text(\"ok\")'",
        task_root=task_root,
        jobs=2,
    )
    elapsed = time.perf_counter() - started

    assert result.exists()
    assert elapsed < 0.85
