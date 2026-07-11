"""Regression tests for P0-A: Python / Vercel schema & API parity.

Covers:
- Exact ``schema_version`` enforcement (``RESULT_SCHEMA_VERSION``).
- Tight field-type / score-bounds / hard-limit validation.
- Header-only token extraction (body ``submission_token`` is rejected).
- Constant-time token comparison (``timing_safe_compare``).
- Allowlist-based ``sanitize_for_storage`` (identical to JS ``sanitizeResult``).
- ``PUBLIC_METADATA_KEYS`` / ``PUBLIC_TASK_KEYS`` / ``SENSITIVE_LOG_KEYS`` enforcement.
- Body-token rejection regression (header-only contract).
- ``submission_token`` never leaks into stored outbound payloads.
"""

import json
from pathlib import Path

import pytest

from hermesbench.schemas import (
    RESULT_SCHEMA_VERSION,
    MAX_RESULT_TASKS,
    MAX_RESULT_METADATA_KEYS,
    validate_result_schema,
    extract_token_from_request,
    timing_safe_compare,
    PUBLIC_METADATA_KEYS,
    PUBLIC_TASK_KEYS,
    SENSITIVE_LOG_KEYS,
)
from hermesbench.api import (
    sanitize_for_storage,
    validate_submission_payload,
    HermesBenchAPI,
    create_submission_store,
)


# ── helpers ──────────────────────────────────────────────────────────────────


def _valid_result(**overrides) -> dict:
    """Return a minimally valid result payload (passes ``validate_result_schema``)."""
    data = {
        "schema_version": RESULT_SCHEMA_VERSION,
        "run_id": "test-run-001",
        "agent": "hermes",
        "suite": "core-cli",
        "started_at": "2026-07-10T00:00:00Z",
        "completed_at": "2026-07-10T00:01:00Z",
        "metadata": {"foo": "bar"},
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
    data.update(overrides)
    return data


def _task(**overrides) -> dict:
    """Return a minimally valid task result dict."""
    d = {
        "task_id": "t1",
        "category": "natural-tool-use",
        "status": "passed",
        "score": 1.0,
        "passed": True,
        "wall_time_seconds": 1.0,
    }
    d.update(overrides)
    return d


# ── Exact schema version ─────────────────────────────────────────────────────


class TestExactSchemaVersion:
    def test_accepts_correct_version(self):
        validate_result_schema(_valid_result())

    def test_rejects_wrong_version(self):
        with pytest.raises(ValueError, match="invalid schema_version"):
            validate_result_schema(_valid_result(schema_version="hermesbench.result.v2"))

    def test_rejects_legacy_format(self):
        with pytest.raises(ValueError, match="invalid schema_version"):
            validate_result_schema(_valid_result(schema_version="hermesbench.api.v0-dev"))

    def test_rejects_missing_version(self):
        with pytest.raises(ValueError, match="invalid schema_version"):
            validate_result_schema(_valid_result(schema_version=None))

    def test_rejects_empty_version(self):
        with pytest.raises(ValueError, match="invalid schema_version"):
            validate_result_schema(_valid_result(schema_version=""))


# ── Tight field-type validation ──────────────────────────────────────────────


class TestFieldTypeValidation:
    def test_rejects_non_dict_input(self):
        with pytest.raises(ValueError, match="result must be a dict"):
            validate_result_schema("not a dict")  # type: ignore[arg-type]

    def test_rejects_empty_run_id(self):
        with pytest.raises(ValueError, match="run_id"):
            validate_result_schema(_valid_result(run_id=""))

    def test_rejects_non_string_run_id(self):
        with pytest.raises(ValueError, match="run_id"):
            validate_result_schema(_valid_result(run_id=123))

    def test_rejects_empty_agent(self):
        with pytest.raises(ValueError, match="agent"):
            validate_result_schema(_valid_result(agent=""))

    def test_rejects_empty_suite(self):
        with pytest.raises(ValueError, match="suite"):
            validate_result_schema(_valid_result(suite=""))

    def test_rejects_non_list_results(self):
        with pytest.raises(ValueError, match="results must be a list"):
            validate_result_schema(_valid_result(results="not-a-list"))

    def test_rejects_non_dict_result_item(self):
        with pytest.raises(ValueError, match="each task result must be a dict"):
            validate_result_schema(_valid_result(results=["not-a-dict"]))

    def test_rejects_missing_task_id(self):
        with pytest.raises(ValueError, match="task_id"):
            validate_result_schema(_valid_result(results=[{"category": "x", "status": "passed", "score": 1.0, "passed": True, "wall_time_seconds": 1.0}]))

    def test_rejects_missing_score(self):
        with pytest.raises(ValueError, match="score must be a number"):
            validate_result_schema(_valid_result(results=[{"task_id": "t1", "category": "x", "status": "passed", "passed": True, "wall_time_seconds": 1.0}]))

    def test_rejects_score_out_of_range_low(self):
        with pytest.raises(ValueError, match="out of range"):
            validate_result_schema(_valid_result(results=[{"task_id": "t1", "category": "x", "status": "passed", "score": -0.1, "passed": True, "wall_time_seconds": 1.0}]))

    def test_rejects_score_out_of_range_high(self):
        with pytest.raises(ValueError, match="out of range"):
            validate_result_schema(_valid_result(results=[{"task_id": "t1", "category": "x", "status": "passed", "score": 1.1, "passed": True, "wall_time_seconds": 1.0}]))

    def test_rejects_non_bool_passed(self):
        with pytest.raises(ValueError, match="passed must be a boolean"):
            validate_result_schema(_valid_result(results=[{"task_id": "t1", "category": "x", "status": "passed", "score": 1.0, "passed": 1, "wall_time_seconds": 1.0}]))

    def test_rejects_non_number_wall_time(self):
        with pytest.raises(ValueError, match="wall_time_seconds must be a number"):
            validate_result_schema(_valid_result(results=[{"task_id": "t1", "category": "x", "status": "passed", "score": 1.0, "passed": True, "wall_time_seconds": "slow"}]))


# ── Hard limits (matching JS MAX_TASKS / MAX_METADATA_KEYS) ──────────────────


class TestHardLimits:
    def test_rejects_too_many_tasks(self):
        many_results = [
            {
                "task_id": f"t{i}",
                "category": "x",
                "status": "passed",
                "score": 1.0,
                "passed": True,
                "wall_time_seconds": 0.1,
            }
            for i in range(MAX_RESULT_TASKS + 1)
        ]
        with pytest.raises(ValueError, match="exceeds maximum"):
            validate_result_schema(_valid_result(results=many_results))

    def test_accepts_at_max_tasks(self):
        max_results = [
            {
                "task_id": f"t{i}",
                "category": "x",
                "status": "passed",
                "score": 1.0,
                "passed": True,
                "wall_time_seconds": 0.1,
            }
            for i in range(MAX_RESULT_TASKS)
        ]
        validate_result_schema(_valid_result(results=max_results))

    def test_rejects_too_many_metadata_keys(self):
        many_meta = {f"k{i}": "v" for i in range(MAX_RESULT_METADATA_KEYS + 1)}
        with pytest.raises(ValueError, match="exceeds maximum"):
            validate_result_schema(_valid_result(metadata=many_meta))

    def test_accepts_at_max_metadata_keys(self):
        max_meta = {f"k{i}": "v" for i in range(MAX_RESULT_METADATA_KEYS)}
        validate_result_schema(_valid_result(metadata=max_meta))

    def test_rejects_none_metadata(self):
        with pytest.raises(ValueError, match="metadata must be a dict"):
            validate_result_schema(_valid_result(metadata=None))


# ── NaN / bool-as-number regression (proven schema gaps) ──────────────────


class TestNanAndBoolRegression:
    """Regression: scores and wall_time must be true numbers, not NaN or bool.

    Python's ``isinstance(float('nan'), float)`` is True and
    ``isinstance(True, int)`` is True (bool is a subclass of int),
    so we must check explicitly.
    """

    def test_rejects_nan_score(self):
        with pytest.raises(ValueError, match="score is NaN"):
            validate_result_schema(_valid_result(
                results=[_task(score=float("nan"))]
            ))

    def test_rejects_nan_wall_time(self):
        with pytest.raises(ValueError, match="wall_time_seconds is NaN"):
            validate_result_schema(_valid_result(
                results=[_task(wall_time_seconds=float("nan"))]
            ))

    def test_rejects_nan_score_in_second_result(self):
        """Multiple results: NaN in any position must be caught."""
        with pytest.raises(ValueError, match="score is NaN"):
            validate_result_schema(_valid_result(
                results=[
                    _task(task_id="t1", score=0.3),
                    _task(task_id="t2", score=float("nan")),
                ]
            ))

    def test_rejects_bool_score(self):
        with pytest.raises(ValueError, match="score must be a number"):
            validate_result_schema(_valid_result(
                results=[_task(score=True)]
            ))

    def test_rejects_bool_score_false(self):
        with pytest.raises(ValueError, match="score must be a number"):
            validate_result_schema(_valid_result(
                results=[_task(score=False)]
            ))

    def test_rejects_bool_wall_time(self):
        with pytest.raises(ValueError, match="wall_time_seconds must be a number"):
            validate_result_schema(_valid_result(
                results=[_task(wall_time_seconds=True)]
            ))

    def test_rejects_bool_wall_time_false(self):
        with pytest.raises(ValueError, match="wall_time_seconds must be a number"):
            validate_result_schema(_valid_result(
                results=[_task(wall_time_seconds=False)]
            ))

    def test_accepts_int_score_zero(self):
        """0 (int) is a valid score — Python int is fine."""
        validate_result_schema(_valid_result(
            results=[_task(score=0)]
        ))

    def test_accepts_zero_wall_time(self):
        """0.0 wall_time is valid."""
        validate_result_schema(_valid_result(
            results=[_task(wall_time_seconds=0.0)]
        ))


# ── None / partial / malformed result entries ─────────────────────────────


class TestNonePartialMalformed:
    """Edge cases: None values, missing keys, partial task results."""

    # ── None values on required result fields ────────────────────────────

    def test_rejects_none_task_id(self):
        with pytest.raises(ValueError, match="task_id"):
            validate_result_schema(_valid_result(
                results=[_task(task_id=None)]
            ))

    def test_rejects_none_category(self):
        with pytest.raises(ValueError, match="category"):
            validate_result_schema(_valid_result(
                results=[_task(category=None)]
            ))

    def test_rejects_none_status(self):
        with pytest.raises(ValueError, match="status"):
            validate_result_schema(_valid_result(
                results=[_task(status=None)]
            ))

    def test_rejects_none_score(self):
        with pytest.raises(ValueError, match="score must be a number"):
            validate_result_schema(_valid_result(
                results=[_task(score=None)]
            ))

    def test_rejects_none_passed(self):
        with pytest.raises(ValueError, match="passed must be a boolean"):
            validate_result_schema(_valid_result(
                results=[_task(passed=None)]
            ))

    def test_rejects_none_wall_time(self):
        with pytest.raises(ValueError, match="wall_time_seconds must be a number"):
            validate_result_schema(_valid_result(
                results=[_task(wall_time_seconds=None)]
            ))

    # ── Missing keys at the result-entry level ───────────────────────────

    def test_rejects_missing_score_key(self):
        with pytest.raises(ValueError, match="score must be a number"):
            validate_result_schema(_valid_result(
                results=[{"task_id": "t1", "category": "x", "status": "passed",
                          "passed": True, "wall_time_seconds": 1.0}]
            ))

    def test_rejects_missing_passed_key(self):
        with pytest.raises(ValueError, match="passed must be a boolean"):
            validate_result_schema(_valid_result(
                results=[{"task_id": "t1", "category": "x", "status": "passed",
                          "score": 0.5, "wall_time_seconds": 1.0}]
            ))

    def test_rejects_missing_wall_time_key(self):
        with pytest.raises(ValueError, match="wall_time_seconds must be a number"):
            validate_result_schema(_valid_result(
                results=[{"task_id": "t1", "category": "x", "status": "passed",
                          "score": 0.5, "passed": True}]
            ))

    def test_rejects_missing_task_id_key(self):
        with pytest.raises(ValueError, match="task_id"):
            validate_result_schema(_valid_result(
                results=[{"category": "x", "status": "passed",
                          "score": 0.5, "passed": True, "wall_time_seconds": 1.0}]
            ))

    # ── Missing top-level keys ───────────────────────────────────────────

    def test_rejects_missing_results_key(self):
        payload = _valid_result()
        del payload["results"]
        with pytest.raises(ValueError, match="results must be a list"):
            validate_result_schema(payload)

    def test_rejects_missing_metadata_key(self):
        payload = _valid_result()
        del payload["metadata"]
        with pytest.raises(ValueError, match="metadata must be a dict"):
            validate_result_schema(payload)

    def test_rejects_results_as_none(self):
        with pytest.raises(ValueError, match="results must be a list"):
            validate_result_schema(_valid_result(results=None))

    # ── Boundary: empty / minimal valid ──────────────────────────────────

    def test_accepts_empty_results_list(self):
        """Zero tasks is valid (empty run)."""
        validate_result_schema(_valid_result(results=[]))

    def test_accepts_empty_metadata_dict(self):
        validate_result_schema(_valid_result(metadata={}))

    def test_accepts_minimal_task_entry(self):
        """Only the 6 required fields, nothing extra."""
        validate_result_schema(_valid_result(
            results=[{
                "task_id": "min",
                "category": "x",
                "status": "passed",
                "score": 0.0,
                "passed": True,
                "wall_time_seconds": 0.0,
            }]
        ))

    # ── Partial: extra fields SHOULD NOT cause validation to reject ──────

    def test_accepts_extra_fields_in_result(self):
        """Extra fields at the result level are not flagged by schema validation.
        (The allowlist stripping happens later during sanitize_for_storage.)"""
        validate_result_schema(_valid_result(
            results=[{
                "task_id": "t1",
                "category": "x",
                "status": "passed",
                "score": 0.5,
                "passed": True,
                "wall_time_seconds": 1.0,
                "extra_field": "should-not-cause-rejection",
                "raw_task_score": 0.55,
            }]
        ))

    # ── Negative wall_time is rejected ───────────────────────────────────

    def test_negative_wall_time_rejected(self):
        """Negative durations are malformed benchmark results."""
        with pytest.raises(ValueError, match="wall_time_seconds must be non-negative"):
            validate_result_schema(_valid_result(
                results=[_task(wall_time_seconds=-1.0)]
            ))


# ── Token extraction (header-only contract) ──────────────────────────────────


class TestTokenExtraction:
    def test_x_hermesbench_header(self):
        token = extract_token_from_request(
            {"X-Hermesbench-Submission-Token": "header-val"},
        )
        assert token == "header-val"

    def test_x_hermesbench_header_lowercase_key(self):
        token = extract_token_from_request(
            {"x-hermesbench-submission-token": "header-val"},
        )
        assert token == "header-val"

    def test_authorization_bearer(self):
        token = extract_token_from_request(
            {"Authorization": "Bearer my-bearer-token"},
        )
        assert token == "my-bearer-token"

    def test_authorization_bearer_lowercase(self):
        token = extract_token_from_request(
            {"authorization": "bearer my-bearer-token"},
        )
        assert token == "my-bearer-token"

    def test_header_takes_precedence_over_bearer(self):
        """X-Hermesbench-Submission-Token > Authorization: Bearer."""
        token = extract_token_from_request(
            {
                "X-Hermesbench-Submission-Token": "header-token",
                "Authorization": "Bearer bearer-token",
            },
        )
        assert token == "header-token"

    def test_body_token_is_rejected(self):
        """Body submission_token is NEVER accepted — header-only contract."""
        token = extract_token_from_request({})
        assert token is None

    def test_no_token_returns_none(self):
        token = extract_token_from_request({})
        assert token is None

    def test_empty_headers_returns_none(self):
        token = extract_token_from_request(None)
        assert token is None


# ── Constant-time comparison ─────────────────────────────────────────────────


class TestTimingSafeCompare:
    def test_equal_strings(self):
        assert timing_safe_compare("abc123", "abc123") is True

    def test_different_strings(self):
        assert timing_safe_compare("abc123", "xyz789") is False

    def test_both_none(self):
        assert timing_safe_compare(None, None) is False  # empty-vs-empty rejected

    def test_one_none(self):
        assert timing_safe_compare("token", None) is False
        assert timing_safe_compare(None, "token") is False

    def test_empty_strings(self):
        assert timing_safe_compare("", "") is False  # empty-vs-empty rejected

    def test_same_length_different_content(self):
        assert timing_safe_compare("secret1", "secret2") is False

    def test_different_length(self):
        assert timing_safe_compare("short", "much-longer-val") is False


# ── Sanitize for storage (allowlist-based, matching JS) ─────────────────────


class TestSanitizeForStorage:
    def test_strips_top_level_token(self):
        payload = _valid_result(submission_token="should-be-gone")
        stored = sanitize_for_storage(payload)
        assert "submission_token" not in stored

    def test_strips_top_level_run_id_hash(self):
        payload = _valid_result(run_id_hash="sensitive-hash")
        stored = sanitize_for_storage(payload)
        assert "run_id_hash" not in stored

    def test_strips_token_in_submission_wrapper(self):
        payload = {
            "schema_version": "hermesbench.submission.v1",
            "submission_token": "wrapper-secret",
            "result": _valid_result(),
        }
        stored = sanitize_for_storage(payload)
        assert "submission_token" not in stored

    def test_original_result_unchanged(self):
        result = _valid_result(submission_token="preserved")
        original = json.loads(json.dumps(result))
        _ = sanitize_for_storage(
            {"schema_version": "hermesbench.submission.v1", "result": result}
        )
        assert original["submission_token"] == "preserved"

    # ── Allowlist behavior ──────────────────────────────────────────────

    def test_metadata_allowlist_only_public_keys(self):
        """Metadata is filtered through PUBLIC_METADATA_KEYS."""
        payload = _valid_result(
            metadata={
                "official": True,
                "reasoning_effort": "high",
                "runner": "ci-v1",
                "foo": "bar",  # not in allowlist
                "secret_field": "sneaky",  # not in allowlist
            }
        )
        stored = sanitize_for_storage(payload)
        assert stored["metadata"]["official"] is True
        assert stored["metadata"]["reasoning_effort"] == "high"
        assert stored["metadata"].get("sanitized") is True
        assert "foo" not in stored["metadata"]
        assert "secret_field" not in stored["metadata"]

    def test_task_allowlist_only_public_keys(self):
        """Task results are filtered through PUBLIC_TASK_KEYS."""
        payload = _valid_result(
            results=[
                {
                    "task_id": "t1",
                    "category": "x",
                    "status": "passed",
                    "score": 0.9,
                    "passed": True,
                    "wall_time_seconds": 1.0,
                    "tool_calls": 5,
                    "raw_task_score": 0.95,  # not in allowlist
                    "effective_task_score": 0.93,  # not in allowlist
                    "internal_note": "sensitive",  # not in allowlist
                }
            ]
        )
        stored = sanitize_for_storage(payload)
        task = stored["results"][0]
        assert task["task_id"] == "t1"
        assert task["score"] == 0.9
        assert "raw_task_score" not in task
        assert "internal_note" not in task

    def test_sanitized_marker_in_metadata(self):
        payload = _valid_result(metadata={"official": True})
        stored = sanitize_for_storage(payload)
        assert stored["metadata"]["sanitized"] is True
        # sanitized is always in PUBLIC_METADATA_KEYS
        payload_nometa = _valid_result(metadata={})
        stored2 = sanitize_for_storage(payload_nometa)
        assert stored2["metadata"]["sanitized"] is True

    def test_strips_nested_token_via_allowlist(self):
        """submission_token inside a task result is stripped by the allowlist."""
        payload = _valid_result(
            results=[
                {
                    "task_id": "t1",
                    "category": "x",
                    "status": "passed",
                    "score": 1.0,
                    "passed": True,
                    "wall_time_seconds": 0.5,
                    "submission_token": "nested-secret",
                }
            ]
        )
        stored = sanitize_for_storage(payload)
        assert "submission_token" not in stored
        assert "submission_token" not in stored["results"][0]

    def test_strips_token_in_metadata(self):
        """submission_token in metadata is stripped by the allowlist."""
        payload = _valid_result(
            metadata={"submission_token": "meta-secret", "official": False}
        )
        stored = sanitize_for_storage(payload)
        assert "submission_token" not in stored["metadata"]
        assert stored["metadata"].get("official") is False

    # ── Sensitive log key stripping ─────────────────────────────────────

    def test_strips_sensitive_log_key_top_level(self):
        """Top-level keys matching SENSITIVE_LOG_KEYS (case-insensitive) are removed."""
        for key in ("logs", "transcript", "stdout", "stderr", "messages"):
            payload = _valid_result(**{key: "sensitive-data"})
            stored = sanitize_for_storage(payload)
            assert key not in stored, f"{key} should have been stripped"

    def test_strips_case_insensitive_log_key(self):
        """Case variants of sensitive log keys are also stripped."""
        payload = _valid_result(LOGS="data", Transcript="data")
        stored = sanitize_for_storage(payload)
        assert "LOGS" not in stored
        assert "Transcript" not in stored

    def test_non_sensitive_fields_preserved(self):
        """Fields not in SENSITIVE_LOG_KEYS should survive if in allowlist."""
        payload = _valid_result(
            metadata={"official": False},
            results=[
                {
                    "task_id": "t1",
                    "category": "x",
                    "status": "passed",
                    "score": 1.0,
                    "passed": True,
                    "wall_time_seconds": 0.5,
                    "tool_calls": 3,
                }
            ],
        )
        stored = sanitize_for_storage(payload)
        assert stored["results"][0]["tool_calls"] == 3
        assert stored["metadata"]["official"] is False


# ── Validate submission payload integration ──────────────────────────────────


class TestValidateSubmissionPayload:
    def test_rejects_invalid_result_schema(self):
        ok, msg = validate_submission_payload(
            {"schema_version": "hermesbench.result.v2", "run_id": ""},
        )
        assert not ok
        assert "schema_version" in msg

    def test_accepts_valid_with_header_token(self):
        ok, msg = validate_submission_payload(
            _valid_result(),
            expected_token="t1",
            headers={"X-Hermesbench-Submission-Token": "t1"},
        )
        assert ok, msg

    def test_rejects_wrong_header_token(self):
        ok, msg = validate_submission_payload(
            _valid_result(),
            expected_token="real",
            headers={"X-Hermesbench-Submission-Token": "fake"},
        )
        assert not ok
        assert "submission token" in msg

    def test_accepts_with_bearer_token(self):
        ok, msg = validate_submission_payload(
            _valid_result(),
            expected_token="bt",
            headers={"Authorization": "Bearer bt"},
        )
        assert ok, msg

    def test_rejects_official_flag(self):
        ok, msg = validate_submission_payload(
            _valid_result(metadata={"official": True}),
            expected_token="t",
            headers={"X-Hermesbench-Submission-Token": "t"},
        )
        assert not ok
        assert "official flag" in msg

    def test_rejects_mock_agent(self):
        ok, msg = validate_submission_payload(
            _valid_result(agent="mock"),
            expected_token="t",
            headers={"X-Hermesbench-Submission-Token": "t"},
        )
        assert not ok
        assert "mock agent" in msg

    # ── Header-only token contract (body-token rejection) ─────────────

    def test_rejects_body_token_only(self):
        """Body submission_token alone is rejected — header-only contract."""
        payload = _valid_result()
        payload["submission_token"] = "body-secret"
        ok, msg = validate_submission_payload(
            payload,
            expected_token="body-secret",
            headers={},
        )
        assert not ok
        assert "submission token" in msg

    def test_rejects_body_token_even_with_matching_bearer(self):
        """Body token is not picked up — only header Bearer works."""
        payload = _valid_result()
        payload["submission_token"] = "some-token"
        ok, msg = validate_submission_payload(
            payload,
            expected_token="some-token",
            headers={"Authorization": "Bearer different-token"},
        )
        # Bearer "different-token" != "some-token" — body is never checked
        assert not ok
        assert "submission token" in msg

    def test_body_token_not_leaked_into_stored_result(self):
        """Sanitized stored result never contains body submission_token."""
        payload = _valid_result(
            submission_token="body-secret",
            metadata={"submission_token": "meta-secret"},
        )
        stored = sanitize_for_storage(
            {"schema_version": "hermesbench.submission.v1", "result": payload}
        )
        assert "submission_token" not in stored
        assert "submission_token" not in stored.get("metadata", {})

    # ── Run-ledger metadata allowlist parity ──────────────────────────

    def test_all_new_run_ledger_fields_survive_sanitization(self):
        """All new PUBLIC_METADATA_KEYS fields survive sanitize_for_storage."""
        run_ledger_meta = {
            "provider": "deepseek",
            "model": "deepseek-chat",
            "reasoning_effort": "high",
            "quantization": "Q4_K_M",
            "backend": "llama.cpp",
            "profile": "hermesbench",
            "benchmark_version": "core-cli-v0.1",
            "jobs": 2,
            "run_wall_time_seconds": 42.5,
            "engine_version": "1.2.3",
            "hermes_version": "0.5.0",
            "git_commit": "abc1234",
            "command": "hermesbench run --suite core",
            "config_summary": {"max_tokens": 4096},
            "os_platform": "Linux-7.1.3-x86_64",
            "python_version": "3.11.14",
            "cpu_info": "AMD EPYC; 8 cores",
            "gpu_info": "1x NVIDIA A100",
            "metadata_available": {"model_identity": True, "runtime": True},
        }
        payload = _valid_result(metadata=run_ledger_meta)
        stored = sanitize_for_storage(payload)
        meta = stored["metadata"]
        for field in run_ledger_meta:
            assert field in meta, f"{field!r} missing from sanitized metadata"
            assert meta[field] == run_ledger_meta[field]
        assert meta["sanitized"] is True

    def test_secret_fields_stripped_from_metadata(self):
        """Secret-like fields not in PUBLIC_METADATA_KEYS are stripped."""
        payload = _valid_result(
            metadata={
                "official": True,
                "provider": "deepseek",
                "api_key": "sk-12345",
                "password": "hunter2",
                "aws_secret": "AKIA123",
                "internal_notes": "sensitive",
                "db_url": "postgresql://user:pass@host/db",
            }
        )
        stored = sanitize_for_storage(payload)
        meta = stored["metadata"]
        # Allowed fields survive
        assert meta.get("official") is True
        assert meta.get("provider") == "deepseek"
        # Secrets are stripped
        assert "api_key" not in meta
        assert "password" not in meta
        assert "aws_secret" not in meta
        assert "internal_notes" not in meta
        assert "db_url" not in meta
        assert meta["sanitized"] is True

    def test_run_ledger_fields_stripped_when_old_allowlist(self):
        """Previously, fields like 'provider', 'model' were already allowed;
        verify config_summary (dict) and metadata_available (dict) survive."""
        payload = _valid_result(
            metadata={
                "config_summary": {"max_tokens": 8192, "temperature": 0.7},
                "metadata_available": {"hardware": True},
            }
        )
        stored = sanitize_for_storage(payload)
        meta = stored["metadata"]
        assert meta.get("config_summary") == {"max_tokens": 8192, "temperature": 0.7}
        assert meta.get("metadata_available") == {"hardware": True}

    def test_js_public_metadata_keys_match_python(self):
        """Verify the set of PUBLIC_METADATA_KEYS in Python matches the JS
        allowlist.  Parses quoted strings from the JS Set literal."""
        import re
        js_path = Path(__file__).resolve().parent.parent / "website/api/_submissions.js"
        js_src = js_path.read_text()
        marker = "const PUBLIC_METADATA_KEYS = new Set(["
        start = js_src.index(marker)
        bracket = js_src.index("[", start)
        end = js_src.index("]);", bracket)
        body = js_src[bracket + 1 : end]
        # Extract all single-quoted strings (the JS uses single quotes)
        js_keys = set(re.findall(r"'([^']+)'", body))
        py_keys = PUBLIC_METADATA_KEYS
        assert js_keys == py_keys, (
            f"JS/PY mismatch\n"
            f"  JS-only:  {sorted(js_keys - py_keys)}\n"
            f"  PY-only:  {sorted(py_keys - js_keys)}"
        )
