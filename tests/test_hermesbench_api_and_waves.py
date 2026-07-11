import json
from pathlib import Path

from hermesbench.api import app, create_submission_store, validate_submission_payload
from hermesbench.tasks import discover_tasks, validate_tasks
from hermesbench.runner import run_benchmark


NATURAL_TASK = "htu-dev-001-file-and-terminal-self-serve"


def test_hermes_core_suite_exists_and_validates():
    assert len(discover_tasks("hermes-core")) == 13
    assert not validate_tasks()


def _result_payload(tmp_path):
    payload = {
        "schema_version": "hermesbench.result.v1",
        "run_id": "test-run",
        "suite": "hermes-core",
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
                "tool_calls": 1,
                "raw_task_score": 1.0,
                "effective_task_score": 1.0,
            }
        ],
    }
    return payload


def _with_header(token: str) -> dict[str, str]:
    return {"X-Hermesbench-Submission-Token": token}


def test_submission_payload_validation_rejects_missing_token(tmp_path):
    payload = _result_payload(tmp_path)
    # No token anywhere — headers omitted entirely
    ok, error = validate_submission_payload(
        payload, expected_token="submit-secret", headers={}
    )
    assert not ok
    assert "submission token" in error


def test_submission_payload_validation_accepts_header_token(tmp_path):
    payload = _result_payload(tmp_path)
    payload["submitter"] = {"name": "mock runner"}
    ok, error = validate_submission_payload(
        payload,
        expected_token="submit-secret",
        headers=_with_header("submit-secret"),
    )
    assert ok, error


def test_submission_payload_validation_accepts_bearer_token(tmp_path):
    payload = _result_payload(tmp_path)
    ok, error = validate_submission_payload(
        payload,
        expected_token="bearer-token",
        headers={"Authorization": "Bearer bearer-token"},
    )
    assert ok, error


def test_submission_payload_body_token_is_rejected(tmp_path):
    """Body submission_token is no longer accepted — header-only contract."""
    payload = _result_payload(tmp_path)
    payload["submission_token"] = "body-secret"
    ok, error = validate_submission_payload(
        payload,
        expected_token="body-secret",
        headers={},
    )
    assert not ok
    assert "submission token" in error


def test_submission_payload_header_takes_precedence_over_bearer(tmp_path):
    payload = _result_payload(tmp_path)
    payload["submission_token"] = "body-wrong"  # no longer relevant
    ok, error = validate_submission_payload(
        payload,
        expected_token="header-right",
        headers=_with_header("header-right"),
    )
    assert ok, error


def test_submission_payload_validation_rejects_wrong_token(tmp_path):
    payload = _result_payload(tmp_path)
    ok, error = validate_submission_payload(
        payload,
        expected_token="real-secret",
        headers=_with_header("wrong-secret"),
    )
    assert not ok
    assert "submission token" in error


def test_api_app_accepts_header_token_and_persists_submission(tmp_path):
    store = create_submission_store(tmp_path / "submissions.jsonl")
    payload = _result_payload(tmp_path)
    response = app.handle_json(
        "POST",
        "/v1/results",
        payload,
        store=store,
        expected_token="submit-secret",
        headers=_with_header("submit-secret"),
    )
    assert response["status"] == 202
    assert response["body"]["run_id"] == payload["run_id"]
    assert store.path.read_text().strip()


def test_api_app_exposes_leaderboard_from_store(tmp_path):
    store = create_submission_store(tmp_path / "submissions.jsonl")
    payload = _result_payload(tmp_path)
    app.handle_json(
        "POST",
        "/v1/results",
        payload,
        store=store,
        expected_token="submit-secret",
        headers=_with_header("submit-secret"),
    )
    response = app.handle_json(
        "GET", "/v1/leaderboard", {}, store=store, expected_token="submit-secret"
    )
    assert response["status"] == 200
    assert response["body"]["entries"][0]["overall_score"] == 1.0
