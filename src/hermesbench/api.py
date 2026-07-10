from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .schemas import (
    RESULT_SCHEMA_VERSION,
    MAX_RESULT_TASKS,
    MAX_RESULT_METADATA_KEYS,
    PUBLIC_METADATA_KEYS,
    PUBLIC_TASK_KEYS,
    PUBLIC_SCORE_FIELDS,
    SENSITIVE_LOG_KEYS,
    extract_token_from_request,
    timing_safe_compare,
    validate_result_schema,
)
from .scoring import aggregate

API_SCHEMA_VERSION = "hermesbench.api.v0-dev"
API_PRODUCTION_READINESS = {
    "server": "wsgiref/local development only; run behind a production WSGI/ASGI server before internet exposure",
    "auth": "shared submission_token placeholder for unofficial uploads; replace with scoped tokens/OIDC for production",
    "rate_limit": "not enforced in-process; configure reverse-proxy/platform limits for POST /v1/results",
    "review_workflow": "public uploads stay unofficial until maintainer review and private/fresh-pack re-run",
}


@dataclass
class SubmissionStore:
    path: Path

    def append(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(payload, sort_keys=True) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        return [
            json.loads(line)
            for line in self.path.read_text().splitlines()
            if line.strip()
        ]


def create_submission_store(
    path: str | Path = "submissions/submissions.jsonl",
) -> SubmissionStore:
    return SubmissionStore(Path(path))


def submission_result(payload: dict[str, Any]) -> dict[str, Any]:
    """Return the result object from either an upload wrapper or legacy raw result."""
    if payload.get("schema_version") == "hermesbench.submission.v1":
        result = payload.get("result")
        if not isinstance(result, dict):
            raise ValueError("missing result field in submission payload")
        return result
    return payload


def validate_submission_payload(
    payload: dict[str, Any],
    *,
    expected_token: str | None = None,
    headers: dict[str, str] | None = None,
) -> tuple[bool, str]:
    try:
        result = submission_result(payload)
    except Exception as exc:
        return False, str(exc)
    try:
        validate_result_schema(result)
    except Exception as exc:
        return False, str(exc)
    # Token from header only — body-token is not accepted.
    token = extract_token_from_request(headers)
    if expected_token and not timing_safe_compare(token, expected_token):
        return False, "missing or invalid submission token"
    if (
        payload.get("classification") == "official"
        or result.get("metadata", {}).get("official") is True
    ):
        return False, "official flag is maintainer-reserved"
    if result.get("agent") == "mock":
        return False, "mock agent submissions are not accepted"
    return True, ""


def sanitize_for_storage(payload: dict[str, Any]) -> dict[str, Any]:
    """Return a deep copy of the result, sanitized via explicit allowlists.

    Matches the JS ``sanitizeResult`` contract using the same
    ``PUBLIC_METADATA_KEYS`` and ``PUBLIC_TASK_KEYS`` allowlists.

    * Strips ``submission_token`` / ``run_id_hash`` at the top level.
    * Strips sensitive log keys (case-insensitive) at the top level.
    * Applies the explicit metadata allowlist (``PUBLIC_METADATA_KEYS``).
    * Applies the explicit task-level allowlist (``PUBLIC_TASK_KEYS``).
    * Sets ``metadata.sanitized = True``.
    """
    stored: dict[str, Any] = json.loads(json.dumps(submission_result(payload)))
    # Top-level sensitive fields always removed.
    stored.pop("submission_token", None)
    stored.pop("run_id_hash", None)
    # Case-insensitive log-key strip at top level (matching JS).
    for key in list(stored):
        if key.lower() in SENSITIVE_LOG_KEYS:
            stored.pop(key, None)

    # Explicit metadata allowlist.
    meta = stored.get("metadata")
    safe_meta: dict[str, Any] = {}
    if isinstance(meta, dict):
        for key in PUBLIC_METADATA_KEYS:
            if key in meta:
                safe_meta[key] = meta[key]
    safe_meta["sanitized"] = True
    stored["metadata"] = safe_meta

    # Explicit task-level allowlist.
    results = stored.get("results")
    if isinstance(results, list):
        stored["results"] = [
            {key: task[key] for key in PUBLIC_TASK_KEYS if key in task}
            for task in results
        ]

    return stored


def _score_payload(payload: dict[str, Any]) -> dict[str, Any]:
    rs = payload["results"]
    n = len(rs) or 1
    overall = sum(r["score"] for r in rs) / n
    entry = {
        "run_id": payload["run_id"],
        "agent": payload["agent"],
        "provider": payload.get("provider") or payload.get("model"),
        "model": payload.get("model"),
        "suite": payload["suite"],
        "overall_score": overall,
        "pass_at_1": sum(1 for r in rs if r.get("passed")) / n,
        "task_count": len(rs),
        "official": bool(payload.get("metadata", {}).get("official")),
        "submitted_at": payload.get("submitted_at") or payload.get("completed_at"),
    }
    # Explicit public field allowlist — strip anything not in PUBLIC_SCORE_FIELDS.
    safe = {k: v for k, v in entry.items() if k in PUBLIC_SCORE_FIELDS}
    return safe


class HermesBenchAPI:
    def handle_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any],
        *,
        store: SubmissionStore | None = None,
        expected_token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        store = store or create_submission_store()
        method = method.upper()
        if method == "POST" and path == "/v1/results":
            ok, error = validate_submission_payload(
                payload, expected_token=expected_token, headers=headers
            )
            if not ok:
                return {"status": 400, "body": {"error": error}}
            stored = sanitize_for_storage(payload)
            store.append(stored)
            return {
                "status": 202,
                "body": {"run_id": stored["run_id"], "accepted": True},
            }
        if method == "GET" and path == "/v1/leaderboard":
            entries = sorted(
                (_score_payload(p) for p in store.read_all()),
                key=lambda e: e["overall_score"],
                reverse=True,
            )
            return {"status": 200, "body": {"entries": entries}}
        if method == "GET" and path == "/health":
            return {"status": 200, "body": {"ok": True}}
        return {"status": 404, "body": {"error": "not found"}}


app = HermesBenchAPI()
