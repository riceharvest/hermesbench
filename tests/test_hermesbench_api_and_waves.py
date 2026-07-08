import json
from pathlib import Path

from hermesbench.api import app, create_submission_store, validate_submission_payload
from hermesbench.tasks import discover_tasks, validate_tasks
from hermesbench.runner import run_benchmark


NATURAL_TASK = 'htu-dev-001-file-and-terminal-self-serve'


def test_natural_tools_dev_suite_exists_and_validates():
    assert len(discover_tasks('natural-tools-dev')) == 5
    assert not validate_tasks()


def _result_payload(tmp_path):
    result_path = run_benchmark(
        agent='mock',
        suite='natural-tools-dev',
        task_id=NATURAL_TASK,
        output_dir=tmp_path,
    )
    payload = json.loads(Path(result_path).read_text())
    # Force the score API to report a perfect deterministic run so leaderboard
    # tests can verify extraction without depending on real tool telemetry.
    payload['results'][0]['score'] = 1.0
    payload['results'][0]['raw_task_score'] = 1.0
    payload['results'][0]['effective_task_score'] = 1.0
    payload['results'][0]['passed'] = True
    return payload


def test_submission_payload_validation_rejects_missing_token(tmp_path):
    payload = _result_payload(tmp_path)
    ok, error = validate_submission_payload(payload, expected_token='submit-secret')
    assert not ok
    assert 'submission_token' in error


def test_submission_payload_validation_accepts_valid_run(tmp_path):
    payload = _result_payload(tmp_path)
    payload['submission_token'] = 'submit-secret'
    payload['submitter'] = {'name': 'mock runner'}
    ok, error = validate_submission_payload(payload, expected_token='submit-secret')
    assert ok, error


def test_api_app_accepts_and_persists_submission(tmp_path):
    store = create_submission_store(tmp_path / 'submissions.jsonl')
    payload = _result_payload(tmp_path)
    payload['submission_token'] = 'submit-secret'
    response = app.handle_json('POST', '/v1/results', payload, store=store, expected_token='submit-secret')
    assert response['status'] == 202
    assert response['body']['run_id'] == payload['run_id']
    assert store.path.read_text().strip()


def test_api_app_exposes_leaderboard_from_store(tmp_path):
    store = create_submission_store(tmp_path / 'submissions.jsonl')
    payload = _result_payload(tmp_path)
    payload['submission_token'] = 'submit-secret'
    app.handle_json('POST', '/v1/results', payload, store=store, expected_token='submit-secret')
    response = app.handle_json('GET', '/v1/leaderboard', {}, store=store, expected_token='submit-secret')
    assert response['status'] == 200
    assert response['body']['entries'][0]['overall_score'] == 1.0
