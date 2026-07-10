import json
import urllib.request
from pathlib import Path

from hermesbench.http_api import create_app
from hermesbench.runner import run_benchmark
from hermesbench.submissions import make_submission_payload


NATURAL_TASK = "htu-dev-001-file-and-terminal-self-serve"


def _payload(tmp_path, official=False):
    payload = {
        "schema_version": "hermesbench.result.v1",
        "run_id": "test-run",
        "suite": "natural-tools-dev",
        "agent": "hermes",
        "model": "test-model",
        "started_at": "2026-07-10T00:00:00Z",
        "completed_at": "2026-07-10T00:01:00Z",
        "metadata": {"official": official},
        "results": [
            {
                "task_id": "t1",
                "category": "natural-tool-use",
                "status": "passed",
                "score": 1.0,
                "passed": True,
                "wall_time_seconds": 1.0,
                "tool_calls": 1,
                "raw_task_score": 1.0,
                "effective_task_score": 1.0,
            }
        ],
    }
    return payload


def test_http_upload_requires_token(tmp_path):
    app = create_app(
        store_path=tmp_path / "submissions.jsonl", submission_token="secret"
    )
    response = app.request("POST", "/v1/results", {"run_id": "bad"})
    assert response.status == 400
    assert (
        "submission_token" in response.json["error"]
        or "missing result field" in response.json["error"]
        or "invalid schema_version" in response.json["error"]
    )


def test_http_valid_upload_strips_token_and_leaderboard(tmp_path):
    app = create_app(
        store_path=tmp_path / "submissions.jsonl", submission_token="secret"
    )
    payload = _payload(tmp_path)
    response = app.request(
        "POST",
        "/v1/results",
        payload,
        headers={"X-Hermesbench-Submission-Token": "secret"},
    )
    assert response.status == 202, response.json
    persisted = json.loads((tmp_path / "submissions.jsonl").read_text().strip())
    assert "submission_token" not in persisted
    # Verify deep-strip — nested submission_token should also be gone
    for key in list(persisted.keys()):
        assert "submission_token" not in (key.lower()), f"found leftover key: {key}"
    leaderboard = app.request("GET", "/v1/leaderboard")
    assert leaderboard.status == 200
    assert leaderboard.json["entries"][0]["overall_score"] == 1.0


def test_http_accepts_bearer_token(tmp_path):
    app = create_app(
        store_path=tmp_path / "submissions.jsonl", submission_token="bearer-token"
    )
    payload = _payload(tmp_path)
    response = app.request(
        "POST",
        "/v1/results",
        payload,
        headers={"Authorization": "Bearer bearer-token"},
    )
    assert response.status == 202, response.json


def test_http_body_token_is_rejected(tmp_path):
    """Body submission_token is no longer accepted — header-only contract."""
    app = create_app(
        store_path=tmp_path / "submissions.jsonl", submission_token="body-token"
    )
    payload = _payload(tmp_path)
    payload["submission_token"] = "body-token"
    response = app.request("POST", "/v1/results", payload, headers={})
    assert response.status == 400
    assert "submission token" in response.json["error"]


def test_http_header_takes_precedence_over_bearer(tmp_path):
    app = create_app(
        store_path=tmp_path / "submissions.jsonl", submission_token="correct"
    )
    payload = _payload(tmp_path)
    payload["submission_token"] = "wrong-body-token"
    response = app.request(
        "POST",
        "/v1/results",
        payload,
        headers={"X-Hermesbench-Submission-Token": "correct"},
    )
    assert response.status == 202, response.json


def test_http_accepts_cli_submission_wrapper(tmp_path):
    app = create_app(
        store_path=tmp_path / "submissions.jsonl", submission_token="secret"
    )
    result_path = tmp_path / "result.json"
    result = {
        "schema_version": "hermesbench.result.v1",
        "run_id": "cli-test-run",
        "suite": "natural-tools-dev",
        "agent": "hermes",
        "model": "test-model",
        "started_at": "2026-07-10T00:00:00Z",
        "completed_at": "2026-07-10T00:01:00Z",
        "metadata": {},
        "results": [
            {
                "task_id": "t1",
                "category": "natural-tool-use",
                "status": "passed",
                "score": 1.0,
                "passed": True,
                "wall_time_seconds": 1.0,
            }
        ],
    }
    result_path.write_text(json.dumps(result))
    result = json.loads(result_path.read_text())
    result_path.write_text(json.dumps(result))
    payload = make_submission_payload(result_path)
    response = app.request(
        "POST",
        "/v1/results",
        payload,
        headers={"X-Hermesbench-Submission-Token": "secret"},
    )
    assert response.status == 202, response.json
    persisted = json.loads((tmp_path / "submissions.jsonl").read_text().strip())
    assert persisted["run_id"] == result["run_id"]
    assert "submission_token" not in persisted


def test_http_rejects_public_official_upload(tmp_path):
    app = create_app(
        store_path=tmp_path / "submissions.jsonl", submission_token="secret"
    )
    payload = _payload(tmp_path, official=True)
    response = app.request(
        "POST",
        "/v1/results",
        payload,
        headers={"X-Hermesbench-Submission-Token": "secret"},
    )
    assert response.status == 400
    assert "official flag" in response.json["error"]


def test_http_health(tmp_path):
    app = create_app(store_path=tmp_path / "submissions.jsonl")
    response = app.request("GET", "/health")
    assert response.status == 200
    assert response.json == {"ok": True}


def test_post_submission_sends_submission_token_header(monkeypatch):
    from hermesbench.submissions import post_submission

    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b'{"accepted":true}'

    def fake_urlopen(req, timeout):
        captured["headers"] = {key.lower(): value for key, value in req.header_items()}
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    body = {"schema_version": "hermesbench.submission.v1", "result": {"run_id": "r1"}}

    assert (
        post_submission(
            body, "https://example.test/v1/results", submission_token="secret-token"
        )
        == '{"accepted":true}'
    )
    assert captured["headers"]["x-hermesbench-submission-token"] == "secret-token"
    assert captured["timeout"] == 30
