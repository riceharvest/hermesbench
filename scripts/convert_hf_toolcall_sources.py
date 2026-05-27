#!/usr/bin/env python3
"""Convert selected HF tool-call traces into compact quarantined source-ready JSONL.

The output is intentionally *not* active train data: the source datasets use
TauBench/ToolScale domain-specific tool namespaces that are outside the current
Hermes v0 action surface. Tool calls are captured in metadata (`source_action`)
and assistant targets remain FINAL-like compact text for quarantine review.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from huggingface_hub import hf_hub_download
import pyarrow.parquet as pq

DATASETS = [
    "jkazdan/taubench_traces_training_data",
    "zake7749/Qwen-3.6-plus-agent-tool-calling-trajectory",
]
QUARANTINE_REASON = "domain tool namespace not in Hermes v0 action surface"
STYLE = "hermes-hf-source-ready-v0"
DEFAULT_OUT = "data/raw/hf/hermes_hf_toolcall_source_ready.v0.jsonl"
DEFAULT_REPORT = "reports/hermes-hf-toolcall-sources-quality.json"

SENSITIVE_KEY_RE = re.compile(
    r"(^|_)(user_?id|client_?id|customer_?id|reservation_?id|booking_?id|confirmation|"
    r"email|address|addr|dob|date_?of_?birth|birth_?date|card|account|iban|ssn|"
    r"passport|phone|telephone|zip|postal|license|token|password|secret)(_|$)",
    re.I,
)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
# Dataset-specific identifiers like olivia_gonzalez_2305, res_123, acct_..., call_...
IDISH_RE = re.compile(
    r"\b(?:[A-Za-z]{2,}_[A-Za-z0-9_]*\d[A-Za-z0-9_]*|(?:user|client|customer|reservation|res|booking|card|acct|account|call)_[A-Za-z0-9_-]+)\b",
    re.I,
)
LONG_NUMBER_RE = re.compile(r"\b(?:\d[ -]?){9,}\d\b")
DOB_RE = re.compile(r"\b(?:19|20)\d{2}[-/](?:0?[1-9]|1[0-2])[-/](?:0?[1-9]|[12]\d|3[01])\b")
XML_THINK_RE = re.compile(r"</?think[^>]*>|reasoning_content", re.I)
WHITESPACE_RE = re.compile(r"\s+")


def compact_text(text: Any, max_chars: int = 700) -> str:
    if text is None:
        return ""
    if not isinstance(text, str):
        text = json.dumps(text, ensure_ascii=False, sort_keys=True)
    text = EMAIL_RE.sub("[REDACTED]", text)
    text = IDISH_RE.sub("[REDACTED]", text)
    text = LONG_NUMBER_RE.sub("[REDACTED]", text)
    text = DOB_RE.sub("[REDACTED]", text)
    # Remove common XML wrapper tags while keeping useful text, mostly for safety in contexts.
    text = re.sub(r"</?(?:instructions|policy|tools?|tool_response|tool_call|function)[^>]*>", " ", text, flags=re.I)
    text = XML_THINK_RE.sub(" ", text)
    text = WHITESPACE_RE.sub(" ", text).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def redact_value(value: Any, key_path: str = "") -> Any:
    sensitive = bool(SENSITIVE_KEY_RE.search(key_path))
    if isinstance(value, dict):
        return {str(k): redact_value(v, f"{key_path}_{k}" if key_path else str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v, key_path) for v in value[:20]]
    if value is None or isinstance(value, bool):
        return value
    if sensitive:
        return "[REDACTED]"
    if isinstance(value, (int, float)):
        return value
    return compact_text(str(value), max_chars=300)


def parse_arguments(raw: Any) -> Any:
    if raw is None:
        return {}
    if isinstance(raw, (dict, list)):
        return redact_value(raw)
    if not isinstance(raw, str):
        return redact_value(raw)
    try:
        parsed = json.loads(raw)
        return redact_value(parsed)
    except Exception:
        return {"_raw": compact_text(raw, max_chars=400)}


def first_tool_call(message: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    calls = message.get("tool_calls") or []
    if not calls:
        return None
    call = calls[0] or {}
    fn = call.get("function") or {}
    name = fn.get("name") or call.get("name")
    if not name:
        return None
    return {"tool": str(name), "arguments": parse_arguments(fn.get("arguments", {}))}


def role_content_message(message: Dict[str, Any]) -> Optional[Dict[str, str]]:
    role = message.get("role")
    if role not in {"user", "assistant"}:
        return None
    if message.get("tool_calls"):
        return None
    content = compact_text(message.get("content"), max_chars=600)
    if not content:
        return None
    # Keep contexts compact and free of assistant target syntax confusion.
    return {"role": role, "content": content}


def context_before(messages: List[Dict[str, Any]], index: int, max_turns: int = 6) -> List[Dict[str, str]]:
    ctx: List[Dict[str, str]] = []
    for m in messages[:index]:
        rc = role_content_message(m)
        if rc:
            ctx.append(rc)
    return ctx[-max_turns:]


def iter_parquet_rows(repo_id: str) -> Iterable[Dict[str, Any]]:
    path = hf_hub_download(repo_id=repo_id, repo_type="dataset", filename="data/train-00000-of-00001.parquet")
    pf = pq.ParquetFile(path)
    for batch in pf.iter_batches(batch_size=128):
        yield from batch.to_pylist()


def make_rows_for_source_record(repo_id: str, record: Dict[str, Any], max_per_record: int = 4) -> Tuple[List[Dict[str, Any]], Counter]:
    out: List[Dict[str, Any]] = []
    counts: Counter = Counter()
    messages = record.get("messages") or []
    if not isinstance(messages, list):
        counts["bad_messages"] += 1
        return out, counts

    for i, message in enumerate(messages):
        if not isinstance(message, dict) or message.get("role") != "assistant":
            continue
        source_action = first_tool_call(message)
        ctx = context_before(messages, i)
        if source_action:
            if not ctx:
                counts["skipped_no_context"] += 1
                continue
            row = {
                "messages": ctx + [{"role": "assistant", "content": "FINAL: Source tool call captured in metadata for quarantine review."}],
                "style": STYLE,
                "source_dataset": repo_id,
                "source_action": source_action,
                "quarantine_reason": QUARANTINE_REASON,
            }
            if record.get("domain"):
                row["source_domain"] = compact_text(record.get("domain"), max_chars=80)
            out.append(row)
            counts["action_rows"] += 1
        else:
            content = compact_text(message.get("content"), max_chars=700)
            if not content:
                counts["skipped_empty_assistant"] += 1
                continue
            if not ctx:
                counts["skipped_no_context"] += 1
                continue
            row = {
                "messages": ctx + [{"role": "assistant", "content": f"FINAL: {content}"}],
                "style": STYLE,
                "source_dataset": repo_id,
                "quarantine_reason": QUARANTINE_REASON,
            }
            if record.get("domain"):
                row["source_domain"] = compact_text(record.get("domain"), max_chars=80)
            out.append(row)
            counts["final_rows"] += 1
        if len(out) >= max_per_record:
            break
    return out, counts


def validate_row(row: Dict[str, Any]) -> List[str]:
    problems: List[str] = []
    if row.get("style") != STYLE:
        problems.append("bad_style")
    if row.get("quarantine_reason") != QUARANTINE_REASON:
        problems.append("missing_quarantine")
    messages = row.get("messages")
    if not isinstance(messages, list) or not messages:
        problems.append("bad_messages")
    else:
        assistant = messages[-1]
        content = assistant.get("content", "") if isinstance(assistant, dict) else ""
        if not content.startswith("FINAL: "):
            problems.append("assistant_not_final")
        if re.search(r"<think|</think|reasoning_content|<tool_call|</tool_call|<tool_response|</tool_response", content, re.I):
            problems.append("raw_reasoning_or_xml")
        if EMAIL_RE.search(content) or IDISH_RE.search(content) or LONG_NUMBER_RE.search(content):
            problems.append("pii_like_assistant_content")
    blob = json.dumps(row, ensure_ascii=False)
    if "call_" in blob:
        problems.append("raw_call_id")
    if EMAIL_RE.search(blob) or LONG_NUMBER_RE.search(blob):
        problems.append("pii_like_blob")
    return problems


def convert(max_rows: int, output_path: Path, report_path: Path) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "style": STYLE,
        "output_path": str(output_path),
        "max_rows": max_rows,
        "quarantine_reason": QUARANTINE_REASON,
        "source_counts": {},
        "skipped_reasons": {},
        "action_rows": 0,
        "final_rows": 0,
        "validation_failures": {},
    }
    all_rows: List[Dict[str, Any]] = []
    per_dataset_target = max(1, max_rows // len(DATASETS))

    for repo_id in DATASETS:
        source_counts = Counter()
        skipped = Counter()
        validation_failures = Counter()
        emitted = 0
        for source_record in iter_parquet_rows(repo_id):
            source_counts["source_records_seen"] += 1
            if emitted >= per_dataset_target and len(all_rows) >= max_rows:
                break
            rows, counts = make_rows_for_source_record(repo_id, source_record)
            skipped.update({k: v for k, v in counts.items() if k.startswith("skipped") or k.startswith("bad")})
            for row in rows:
                if len(all_rows) >= max_rows or emitted >= per_dataset_target:
                    break
                problems = validate_row(row)
                if problems:
                    validation_failures.update(problems)
                    skipped["validation_failed"] += 1
                    continue
                all_rows.append(row)
                emitted += 1
                if "source_action" in row:
                    source_counts["action_rows"] += 1
                    report["action_rows"] += 1
                else:
                    source_counts["final_rows"] += 1
                    report["final_rows"] += 1
        source_counts["emitted_rows"] = emitted
        report["source_counts"][repo_id] = dict(source_counts)
        report["skipped_reasons"][repo_id] = dict(skipped)
        report["validation_failures"][repo_id] = dict(validation_failures)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for row in all_rows:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    report["total_rows"] = len(all_rows)
    report["datasets"] = DATASETS
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, sort_keys=True)
        f.write("\n")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-rows", type=int, default=300)
    parser.add_argument("--output", type=Path, default=Path(DEFAULT_OUT))
    parser.add_argument("--report", type=Path, default=Path(DEFAULT_REPORT))
    args = parser.parse_args()
    report = convert(args.max_rows, args.output, args.report)
    print(json.dumps({
        "output_path": report["output_path"],
        "report_path": str(args.report),
        "total_rows": report["total_rows"],
        "action_rows": report["action_rows"],
        "final_rows": report["final_rows"],
    }, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
