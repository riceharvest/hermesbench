import json
from pathlib import Path

from hermesbench.api import app, create_submission_store, validate_submission_payload
from hermesbench.tasks import discover_tasks, validate_tasks
from hermesbench.runner import run_benchmark


def test_private_fresh_anchor_waves_exist_and_validate():
    assert len(discover_tasks('private-holdout')) >= 5
    assert len(discover_tasks('fresh-rolling')) >= 5
    assert len(discover_tasks('anchor')) >= 5
    assert not validate_tasks()


def test_submission_payload_validation_rejects_missing_token(tmp_path):
    result_path = run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path)
    payload = json.loads(Path(result_path).read_text())
    ok, error = validate_submission_payload(payload, expected_token='submit-secret')
    assert not ok
    assert 'submission_token' in error


def test_submission_payload_validation_accepts_valid_run(tmp_path):
    result_path = run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path)
    payload = json.loads(Path(result_path).read_text())
    payload['submission_token'] = 'submit-secret'
    payload['submitter'] = {'name': 'mock runner'}
    ok, error = validate_submission_payload(payload, expected_token='submit-secret')
    assert ok, error


def test_api_app_accepts_and_persists_submission(tmp_path):
    store = create_submission_store(tmp_path / 'submissions.jsonl')
    result_path = run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path)
    payload = json.loads(Path(result_path).read_text())
    payload['submission_token'] = 'submit-secret'
    response = app.handle_json('POST', '/v1/results', payload, store=store, expected_token='submit-secret')
    assert response['status'] == 202
    assert response['body']['run_id'] == payload['run_id']
    assert store.path.read_text().strip()


def test_api_app_exposes_leaderboard_from_store(tmp_path):
    store = create_submission_store(tmp_path / 'submissions.jsonl')
    result_path = run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path)
    payload = json.loads(Path(result_path).read_text())
    payload['submission_token'] = 'submit-secret'
    app.handle_json('POST', '/v1/results', payload, store=store, expected_token='submit-secret')
    response = app.handle_json('GET', '/v1/leaderboard', {}, store=store, expected_token='submit-secret')
    assert response['status'] == 200
    assert response['body']['entries'][0]['overall_score'] == 1.0
