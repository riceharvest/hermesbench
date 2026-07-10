from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from wsgiref.simple_server import make_server

from .api import API_SCHEMA_VERSION, HermesBenchAPI, create_submission_store


@dataclass
class HTTPResponse:
    status: int
    json: dict[str, Any]
    headers: dict[str, str]


def _wsgi_headers(environ: dict[str, Any]) -> dict[str, str]:
    """Extract HTTP headers from a WSGI environ dict.

    WSGI prefixes HTTP headers with ``HTTP_`` and uppercases + hyphenifies
    them.  ``CONTENT_TYPE`` and ``CONTENT_LENGTH`` are special-cased by WSGI
    and do *not* get the ``HTTP_`` prefix.
    """
    headers: dict[str, str] = {}
    for key, value in environ.items():
        if key.startswith("HTTP_"):
            header_name = key[5:].replace("_", "-").title()
            headers[header_name] = value
    # CONTENT_TYPE and CONTENT_LENGTH are special WSGI keys
    if "CONTENT_TYPE" in environ:
        headers["Content-Type"] = environ["CONTENT_TYPE"]
    if "CONTENT_LENGTH" in environ:
        headers["Content-Length"] = environ["CONTENT_LENGTH"]
    return headers


class HermesBenchHTTPApp:
    def __init__(self, *, store_path: str | Path = "submissions/submissions.jsonl", submission_token: str | None = None):
        self.store = create_submission_store(store_path)
        self.submission_token = submission_token
        self.core = HermesBenchAPI()

    def request(self, method: str, path: str, json_body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> HTTPResponse:
        result = self.core.handle_json(method, path, json_body or {}, store=self.store, expected_token=self.submission_token, headers=headers)
        return HTTPResponse(result["status"], result["body"], {"content-type": "application/json", "x-hermesbench-api-schema": API_SCHEMA_VERSION, "x-hermesbench-dev-only": "true"})

    def __call__(self, environ: dict[str, Any], start_response) -> Iterable[bytes]:
        length = int(environ.get("CONTENT_LENGTH") or 0)
        raw = environ["wsgi.input"].read(length) if length else b""
        try:
            payload = json.loads(raw.decode("utf-8")) if raw else {}
        except json.JSONDecodeError:
            payload = {}
        headers = _wsgi_headers(environ)
        response = self.request(environ.get("REQUEST_METHOD", "GET"), environ.get("PATH_INFO", "/"), payload, headers=headers)
        reason = "OK" if response.status < 400 else "Bad Request" if response.status == 400 else "Not Found"
        body = json.dumps(response.json).encode("utf-8")
        start_response(f"{response.status} {reason}", [(k.title(), v) for k, v in {**response.headers, "Content-Length": str(len(body))}.items()])
        return [body]

    def serve(self, host: str = "127.0.0.1", port: int = 8787) -> None:
        with make_server(host, port, self) as httpd:
            httpd.serve_forever()


def create_app(*, store_path: str | Path = "submissions/submissions.jsonl", submission_token: str | None = None) -> HermesBenchHTTPApp:
    return HermesBenchHTTPApp(store_path=store_path, submission_token=submission_token)
