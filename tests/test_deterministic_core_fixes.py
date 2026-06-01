import json
from pathlib import Path

from hermesbench.graders.deterministic import run_checks
from hermesbench.tasks import discover_tasks, validate_tasks
from hermesbench.runner import run_benchmark


def test_deterministic_extended_assertions(tmp_path):
    (tmp_path/'out').mkdir()
    (tmp_path/'out/report.json').write_text(json.dumps({'a': {'b': [{'value': 10.01}]}, 'name': 'alpha'}))
    (tmp_path/'out/log.txt').write_text('hello build-123\n')
    checks=[
        {'type':'json_field','path':'out/report.json','expr':'a.b[0].value~=10±0.05'},
        {'type':'json_field','path':'out/report.json','expr':'a.b[0].value>=10'},
        {'type':'artifact_matches','path':'out/log.txt','pattern':r'build-\d+'},
        {'type':'artifact_not_contains','path':'out/log.txt','needle':'SECRET'},
        {'type':'glob_exists','pattern':'out/*.txt'},
        {'type':'command_contains','command':'printf ok','needle':'ok','timeout_seconds':1},
        {'type':'command_not_contains','command':'printf safe','needle':'SECRET','timeout_seconds':1},
    ]
    score, evidence = run_checks(tmp_path, checks)
    assert score == 1.0
    assert all('PASS' in e for e in evidence)


def test_manifest_is_authoritative_and_validates_extra(tmp_path):
    tasks_dir=tmp_path/'tasks'; suite=tasks_dir/'public-dev'; suite.mkdir(parents=True)
    md='''---\nid: listed\ntitle: Listed\ncategory: cat\nwave: 1\nvisibility: public\ncreated_at: 2026-01-01\nfreshness_window: static\nexpected_human_minutes: 1\ndifficulty: easy\nrequired_toolsets: []\ngrading_type: deterministic\ntimeout_seconds: 10\ncontamination_notes: note long enough\nsafety_notes: none\n---\n## Prompt\nDo it.\n## Deterministic checks\n- artifact_exists: done.txt\n'''
    (suite/'listed.md').write_text(md)
    (suite/'extra.md').write_text(md.replace('id: listed','id: extra'))
    (tasks_dir/'manifest.yaml').write_text('suite: public-dev\ntasks:\n- id: listed\n  path: public-dev/listed.md\n  category: cat\n  visibility: public\n')
    tasks=discover_tasks('public-dev', task_root=tasks_dir)
    assert [t.metadata['id'] for t in tasks] == ['listed']
    assert any('extra.md missing from manifest' in e for e in validate_tasks(task_root=tasks_dir))


def test_result_exposes_effective_scoring_and_sandbox(tmp_path):
    result=run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path)
    data=json.loads(Path(result).read_text())
    r=data['results'][0]
    for key in ['raw_task_score','effective_task_score','behavior_penalty','passed_raw','passed_effective','verification_claimed','verification_sufficient']:
        assert key in r
    assert r['raw_task_score'] == 1.0
    assert r['effective_task_score'] == 1.0
    assert r['logs']['sandbox']['env_policy']['mode'] == 'allowlist+scrub'
