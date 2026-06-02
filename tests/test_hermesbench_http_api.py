import json
from pathlib import Path

from hermesbench.http_api import create_app
from hermesbench.runner import run_benchmark
from hermesbench.submissions import make_submission_payload


def _payload(tmp_path, official=False):
    result_path = run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path)
    payload = json.loads(Path(result_path).read_text())
    payload['submission_token'] = 'secret'
    payload.setdefault('metadata', {})['official'] = official
    return payload


def test_http_upload_requires_token(tmp_path):
    app = create_app(store_path=tmp_path / 'submissions.jsonl', submission_token='secret')
    response = app.request('POST', '/v1/results', {'run_id': 'bad'})
    assert response.status == 400
    assert 'submission_token' in response.json['error'] or 'missing result field' in response.json['error']


def test_http_valid_upload_strips_token_and_leaderboard(tmp_path):
    app = create_app(store_path=tmp_path / 'submissions.jsonl', submission_token='secret')
    payload = _payload(tmp_path)
    response = app.request('POST', '/v1/results', payload)
    assert response.status == 202
    persisted = json.loads((tmp_path / 'submissions.jsonl').read_text().strip())
    assert 'submission_token' not in persisted
    leaderboard = app.request('GET', '/v1/leaderboard')
    assert leaderboard.status == 200
    assert leaderboard.json['entries'][0]['overall_score'] == 1.0


def test_http_accepts_cli_submission_wrapper(tmp_path):
    app = create_app(store_path=tmp_path / 'submissions.jsonl', submission_token='secret')
    result_path = Path(run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path))
    result = json.loads(result_path.read_text())
    result['submission_token'] = 'secret'
    result_path.write_text(json.dumps(result))
    payload = make_submission_payload(result_path)
    response = app.request('POST', '/v1/results', payload)
    assert response.status == 202
    persisted = json.loads((tmp_path / 'submissions.jsonl').read_text().strip())
    assert persisted['run_id'] == result['run_id']
    assert 'submission_token' not in persisted


def test_http_rejects_public_official_upload(tmp_path):
    app = create_app(store_path=tmp_path / 'submissions.jsonl', submission_token='secret')
    response = app.request('POST', '/v1/results', _payload(tmp_path, official=True))
    assert response.status == 400
    assert 'official flag' in response.json['error']


def test_http_health(tmp_path):
    app = create_app(store_path=tmp_path / 'submissions.jsonl')
    response = app.request('GET', '/health')
    assert response.status == 200
    assert response.json == {'ok': True}
