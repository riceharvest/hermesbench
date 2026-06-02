from __future__ import annotations
import json, os, urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from .schemas import validate_result_schema
from .scoring import aggregate

SENSITIVE_LOG_KEYS = {"transcript", "stdout", "stderr", "logs", "messages"}


def load_result(path: str | Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text())
    validate_result_schema(data)
    return data


def sanitize_result(data: dict[str, Any], strip_logs: bool = True) -> dict[str, Any]:
    clean = json.loads(json.dumps(data))
    if strip_logs:
        for task in clean.get("results", []):
            task.pop("logs", None)
            for key in list(task.keys()):
                if key.lower() in SENSITIVE_LOG_KEYS:
                    task.pop(key, None)
    clean.setdefault("metadata", {})["sanitized"] = bool(strip_logs)
    return clean


def make_submission_payload(result_path: str | Path, strip_logs: bool = True) -> dict[str, Any]:
    result_path = Path(result_path)
    data = sanitize_result(load_result(result_path), strip_logs=strip_logs)
    tmp = result_path.parent / (result_path.stem + ".sanitized.json")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    score = aggregate(tmp)
    tmp.unlink(missing_ok=True)
    classification = "official" if data.get("metadata", {}).get("official") is True else "unofficial"
    return {
        "schema_version": "hermesbench.submission.v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "classification": classification,
        "result": data,
        "score": score,
        "github_issue": {
            "title": f"HermesBench submission: {data.get('agent')} {data.get('model') or ''} ({data.get('suite')})".strip(),
            "labels": ["hermesbench-submission", classification],
            "body": "Please review this sanitized HermesBench submission. Public-dev submissions are unofficial unless accompanied by maintainer-issued private pack manifests.\n\n```json\n" + json.dumps({"run_id": data.get("run_id"), "score": score, "classification": classification}, indent=2) + "\n```",
        },
    }


def write_submission_file(payload: dict[str, Any], output_dir: str | Path = "submissions") -> Path:
    out = Path(output_dir); out.mkdir(parents=True, exist_ok=True)
    run_id = payload.get("result", {}).get("run_id", "unknown")
    path = out / f"submission-{run_id}.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True))
    return path


def post_submission(payload: dict[str, Any], endpoint: str, submission_token: str | None = None) -> str:
    body = json.dumps(payload).encode("utf-8")
    headers = {"content-type": "application/json"}
    token = submission_token or os.environ.get("HERMESBENCH_SUBMISSION_TOKEN")
    if token:
        headers["x-hermesbench-submission-token"] = token
    req = urllib.request.Request(endpoint, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=30) as resp:  # nosec - caller supplied local/API endpoint
        return resp.read().decode("utf-8")
