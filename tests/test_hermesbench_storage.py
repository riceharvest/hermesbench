import json
from pathlib import Path

import pytest

from hermesbench.runner import run_benchmark
from hermesbench.storage import SQLiteSubmissionStore, create_sqlite_store


def _payload(tmp_path, run_id='run-1', score=1.0, official=False):
    result_path = run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path)
    payload = json.loads(Path(result_path).read_text())
    payload['run_id'] = run_id
    payload['submission_token'] = 'secret'
    payload.setdefault('metadata', {})['official'] = official
    payload['results'][0]['score'] = score
    payload['results'][0]['passed'] = score >= 1.0
    return payload


def test_sqlite_store_inserts_submission_and_strips_token(tmp_path):
    store = create_sqlite_store(tmp_path / 'submissions.db')
    store.append(_payload(tmp_path))
    rows = store.read_all()
    assert rows[0]['run_id'] == 'run-1'
    assert 'submission_token' not in rows[0]


def test_sqlite_store_rejects_duplicate_run_id(tmp_path):
    store = SQLiteSubmissionStore(tmp_path / 'submissions.db')
    payload = _payload(tmp_path)
    store.append(payload)
    with pytest.raises(ValueError, match='duplicate run_id'):
        store.append(payload)


def test_sqlite_leaderboard_sorted_and_filterable(tmp_path):
    store = create_sqlite_store(tmp_path / 'submissions.db')
    store.append(_payload(tmp_path, run_id='low', score=0.25, official=False))
    store.append(_payload(tmp_path, run_id='high', score=1.0, official=True))
    assert [r['run_id'] for r in store.leaderboard()] == ['high', 'low']
    assert [r['run_id'] for r in store.leaderboard(official=True)] == ['high']
    assert [r['run_id'] for r in store.leaderboard(official=False)] == ['low']
