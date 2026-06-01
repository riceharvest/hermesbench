from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from wsgiref.simple_server import make_server

from .api import HermesBenchAPI, create_submission_store


@dataclass
class HTTPResponse:
    status: int
    json: dict[str, Any]
    headers: dict[str, str]


class HermesBenchHTTPApp:
    def __init__(self, *, store_path: str | Path = 'submissions/submissions.jsonl', submission_token: str | None = None):
        self.store = create_submission_store(store_path)
        self.submission_token = submission_token
        self.core = HermesBenchAPI()

    def request(self, method: str, path: str, json_body: dict[str, Any] | None = None) -> HTTPResponse:
        result = self.core.handle_json(method, path, json_body or {}, store=self.store, expected_token=self.submission_token)
        return HTTPResponse(result['status'], result['body'], {'content-type': 'application/json'})

    def __call__(self, environ: dict[str, Any], start_response) -> Iterable[bytes]:
        length = int(environ.get('CONTENT_LENGTH') or 0)
        raw = environ['wsgi.input'].read(length) if length else b''
        try:
            payload = json.loads(raw.decode('utf-8')) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        response = self.request(environ.get('REQUEST_METHOD', 'GET'), environ.get('PATH_INFO', '/'), payload)
        reason = 'OK' if response.status < 400 else 'Bad Request' if response.status == 400 else 'Not Found'
        body = json.dumps(response.json).encode('utf-8')
        start_response(f'{response.status} {reason}', [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))])
        return [body]

    def serve(self, host: str = '127.0.0.1', port: int = 8787) -> None:
        with make_server(host, port, self) as httpd:
            httpd.serve_forever()


def create_app(*, store_path: str | Path = 'submissions/submissions.jsonl', submission_token: str | None = None) -> HermesBenchHTTPApp:
    return HermesBenchHTTPApp(store_path=store_path, submission_token=submission_token)
