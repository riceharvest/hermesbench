from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import validate_result_schema
from .scoring import aggregate

API_SCHEMA_VERSION = 'hermesbench.api.v0-dev'
API_PRODUCTION_READINESS = {
    'server': 'wsgiref/local development only; run behind a production WSGI/ASGI server before internet exposure',
    'auth': 'shared submission_token placeholder for unofficial uploads; replace with scoped tokens/OIDC for production',
    'rate_limit': 'not enforced in-process; configure reverse-proxy/platform limits for POST /v1/results',
    'review_workflow': 'public uploads stay unofficial until maintainer review and private/fresh-pack re-run',
}


@dataclass
class SubmissionStore:
    path: Path

    def append(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open('a') as f:
            f.write(json.dumps(payload, sort_keys=True) + '\n')

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [json.loads(line) for line in self.path.read_text().splitlines() if line.strip()]


def create_submission_store(path: str | Path = 'submissions/submissions.jsonl') -> SubmissionStore:
    return SubmissionStore(Path(path))


def submission_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the result object from either an upload wrapper or legacy raw result."""
    if payload.get('schema_version') == 'hermesbench.submission.v1':
        result = payload.get('result')
        if not isinstance(result, dict):
            raise ValueError('missing result field in submission payload')
        return result
    return payload


def validate_submission_payload(payload: dict[str, Any], expected_token: str | None = None) -> tuple[bool, str]:
    try:
        result = submission_result(payload)
    except Exception as exc:
        return False, str(exc)
    try:
        validate_result_schema(result)
    except Exception as exc:
        return False, str(exc)
    token = payload.get('submission_token') or result.get('submission_token')
    if expected_token and token != expected_token:
        return False, 'missing or invalid submission_token'
    if payload.get('classification') == 'official' or result.get('metadata', {}).get('official') is True:
        return False, 'official flag is maintainer-reserved'
    return True, ''


def sanitize_for_storage(payload: dict[str, Any]) -> dict[str, Any]:
    stored = dict(submission_result(payload))
    stored.pop('submission_token', None)
    return stored


def _score_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rs = payload['results']
    n = len(rs) or 1
    overall = sum(r['score'] for r in rs) / n
    return {
        'run_id': payload['run_id'],
        'agent': payload['agent'],
        'model': payload.get('model'),
        'suite': payload['suite'],
        'overall_score': overall,
        'pass_at_1': sum(1 for r in rs if r.get('passed')) / n,
        'task_count': len(rs),
        'official': bool(payload.get('metadata', {}).get('official')),
        'submitted_at': payload.get('submitted_at') or payload.get('completed_at'),
    }


class HermesBenchAPI:
    def handle_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        store: SubmissionStore | None = None,
        expected_token: str | None = None,
    ) -> dict[str, Any]:
        store = store or create_submission_store()
        method = method.upper()
        if method == 'POST' and path == '/v1/results':
            ok, error = validate_submission_payload(payload, expected_token=expected_token)
            if not ok:
                return {'status': 400, 'body': {'error': error}}
            stored = sanitize_for_storage(payload)
            store.append(stored)
            return {'status': 202, 'body': {'run_id': stored['run_id'], 'accepted': True}}
        if method == 'GET' and path == '/v1/leaderboard':
            entries = sorted((_score_payload(p) for p in store.read_all()), key=lambda e: e['overall_score'], reverse=True)
            return {'status': 200, 'body': {'entries': entries}}
        if method == 'GET' and path == '/health':
            return {'status': 200, 'body': {'ok': True}}
        return {'status': 404, 'body': {'error': 'not found'}}


app = HermesBenchAPI()
