from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import validate_result_schema
from .scoring import aggregate


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


def validate_submission_payload(payload: dict[str, Any], expected_token: str | None = None) -> tuple[bool, str]:
    try:
        validate_result_schema(payload)
    except Exception as exc:
        return False, str(exc)
    if expected_token and payload.get('submission_token') != expected_token:
        return False, 'missing or invalid submission_token'
    if payload.get('metadata', {}).get('official') is True:
        return False, 'official flag is maintainer-reserved'
    return True, ''


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
            stored = dict(payload)
            stored.pop('submission_token', None)
            store.append(stored)
            return {'status': 202, 'body': {'run_id': payload['run_id'], 'accepted': True}}
        if method == 'GET' and path == '/v1/leaderboard':
            entries = sorted((_score_payload(p) for p in store.read_all()), key=lambda e: e['overall_score'], reverse=True)
            return {'status': 200, 'body': {'entries': entries}}
        if method == 'GET' and path == '/health':
            return {'status': 200, 'body': {'ok': True}}
        return {'status': 404, 'body': {'error': 'not found'}}


app = HermesBenchAPI()
