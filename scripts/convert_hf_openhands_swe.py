#!/usr/bin/env python3
"""Convert SWE-Gym/OpenHands success trajectories to Hermes ultra-compact JSONL.

Usage:
  uv run --with duckdb --with huggingface_hub python scripts/convert_hf_openhands_swe.py \
    --output data/examples/hermes_hf_openhands_swe.v0.jsonl \
    --report reports/hermes-hf-openhands-swe-quality.json \
    --limit 300 --min-rows 100

The converter reads the `train.success.oss` parquet shard from
`SWE-Gym/OpenHands-SFT-Trajectories`, emits one SFT example per convertible
assistant turn, validates each assistant target with Hermes ultra-compact v0,
and writes a JSON quality report with skip reasons and target distributions.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import duckdb
from huggingface_hub import hf_hub_url

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from qwen_mtp_probe.ultra_compact import STYLE_NAME, validate_ultra_compact_assistant

DATASET = "SWE-Gym/OpenHands-SFT-Trajectories"
PARQUET_FILE = "data/train.success.oss-00000-of-00001.parquet"
SOURCE_SPLIT = "train.success.oss"
MAX_ACTION_JSON_CHARS = 12000
MAX_CONTEXT_CHARS = 12000
SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"(?:postgres|mysql|mongodb)://[^\s\"']+:[^\s\"']+@", re.I),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
]
XML_BANNED_IN_TARGET = ("<function=", "</function>", "<think", "analysis", "plan")
RISKY_BASH_RE = re.compile(
    r"(?ix)(\brm\b|\bfind\b[^\n]*(?:-delete|-exec\s+rm\b|xargs\s+rm\b)|\b(?:mkfs|fdisk|dd|chmod|chown)\b)"
)


def redact(text: str) -> str:
    for pattern in SECRET_PATTERNS:
        text = pattern.sub("[REDACTED]", text)
    return text


def compact_text(text: str, *, limit: int = MAX_CONTEXT_CHARS) -> str:
    text = redact(text).replace("\x00", "")
    text = re.sub(r"\n{4,}", "\n\n\n", text).strip()
    if len(text) > limit:
        return text[:limit].rstrip() + "\n[truncated]"
    return text


def parse_function_xml(content: str) -> tuple[str, dict[str, Any]] | None:
    match = re.search(r"<function=([A-Za-z_][A-Za-z0-9_]*)>(.*?)</function>", content, re.S)
    if not match:
        return None
    name = match.group(1)
    body = match.group(2)
    args: dict[str, Any] = {}
    for param, raw in re.findall(r"<parameter=([A-Za-z_][A-Za-z0-9_]*)>(.*?)</parameter>", body, re.S):
        value = raw.strip()
        if param in {"view_range"}:
            try:
                args[param] = json.loads(value)
                continue
            except json.JSONDecodeError:
                pass
        if param == "insert_line":
            try:
                args[param] = int(value)
                continue
            except ValueError:
                pass
        args[param] = value
    return name, args


def is_probably_dir_view(next_observation: str, path: str) -> bool:
    if "files and directories" in next_observation or "excluding hidden items" in next_observation:
        return True
    base = Path(path.rstrip("/")).name
    if "." in base and not base.startswith("."):
        return False
    if re.search(r"/(README|LICENSE|Makefile|Dockerfile|pyproject\.toml|setup\.cfg)$", path):
        return False
    return True


def infer_workdir(command: str) -> str | None:
    cd_match = re.match(r"\s*cd\s+([^;&|]+)\s*(?:&&|;)", command)
    if cd_match:
        return cd_match.group(1).strip().strip("'\"")
    ws_match = re.search(r"(/workspace/[^\s'\";&|)]+)", command)
    if ws_match:
        candidate = ws_match.group(1).rstrip(".,:")
        # If the command references a file path, use its parent; otherwise use the path itself.
        base = Path(candidate).name
        if "." in base and not base.startswith("."):
            return str(Path(candidate).parent)
        return candidate
    return None


def action(tool: str, args: dict[str, Any]) -> str | None:
    raw = json.dumps(args, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(raw) > MAX_ACTION_JSON_CHARS:
        return None
    target = f"ACTION {tool} {raw}"
    validate_ultra_compact_assistant(target)
    parsed = re.match(r"^ACTION\s+\w+\s+(\{.*\})$", target, re.S)
    if not parsed or not isinstance(json.loads(parsed.group(1)), dict):
        return None
    if any(marker in target for marker in XML_BANNED_IN_TARGET):
        return None
    return target


def convert_tool_call(name: str, args: dict[str, Any], next_observation: str) -> tuple[str | None, str]:
    if name == "execute_bash":
        command = redact(str(args.get("command", ""))).strip()
        if not command:
            return None, "empty_bash_command"
        if RISKY_BASH_RE.search(command):
            return None, "risky_bash_command"
        payload: dict[str, Any] = {"command": command}
        workdir = infer_workdir(command)
        if workdir:
            payload["workdir"] = workdir
        return action("terminal", payload), "execute_bash"

    if name == "finish":
        target = "FINAL: Completed after verification."
        validate_ultra_compact_assistant(target)
        return target, "finish"

    if name != "str_replace_editor":
        return None, f"unsupported_tool:{name}"

    command = str(args.get("command", "")).strip()
    path = redact(str(args.get("path", "")).strip())
    if not path:
        return None, "missing_editor_path"

    if command == "view":
        if is_probably_dir_view(next_observation, path):
            return action("search_files", {"target": "files", "pattern": "*", "path": path, "limit": 50}), "view_dir"
        view_range = args.get("view_range")
        offset = 1
        limit = 500
        if isinstance(view_range, list) and view_range:
            try:
                start = max(1, int(view_range[0]))
                end = int(view_range[1]) if len(view_range) > 1 else start + 499
                offset = start
                limit = 500 if end == -1 else max(1, min(500, end - start + 1))
            except (TypeError, ValueError):
                pass
        return action("read_file", {"path": path, "offset": offset, "limit": limit}), "view_file"

    if command == "str_replace":
        old = redact(str(args.get("old_str", "")))
        new = redact(str(args.get("new_str", "")))
        if not old:
            return None, "missing_old_str"
        payload = {"path": path, "old_string": old, "new_string": new}
        return action("patch", payload), "str_replace"

    if command == "create":
        content = redact(str(args.get("file_text", "")))
        if not content:
            return None, "missing_file_text"
        return action("write_file", {"path": path, "content": content}), "create"

    return None, f"unsupported_editor_command:{command or 'missing'}"


def output_kind(target: str) -> str:
    if target.startswith("ACTION "):
        return "action_only"
    if target.startswith("FINAL:"):
        return "final_only"
    if target.startswith("SCRATCH<=32:"):
        return "scratch_action" if "\n\nACTION " in target else "scratch_final"
    return "invalid"


def output_tool(target: str) -> str | None:
    match = re.match(r"ACTION\s+([A-Za-z_][A-Za-z0-9_]*)\s+", target)
    return match.group(1) if match else None


def build_context(messages: list[dict[str, str]], assistant_index: int) -> list[dict[str, str]]:
    prior = messages[:assistant_index]
    first_user = next((m for m in prior if m.get("role") == "user"), None)
    last_user = next((m for m in reversed(prior) if m.get("role") == "user"), None)
    out: list[dict[str, str]] = []
    if first_user:
        out.append({"role": "user", "content": compact_text(first_user["content"])})
    if last_user and last_user is not first_user:
        out.append({"role": "user", "content": compact_text(last_user["content"], limit=6000)})
    return out


def fetch_source_rows(limit_source_rows: int | None = None) -> list[list[dict[str, str]]]:
    url = hf_hub_url(DATASET, PARQUET_FILE, repo_type="dataset")
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    sql = "SELECT messages FROM read_parquet(?)"
    if limit_source_rows:
        sql += f" LIMIT {int(limit_source_rows)}"
    return [row[0] for row in con.execute(sql, [url]).fetchall()]


def convert(limit: int, limit_source_rows: int | None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    by_tool: Counter[str] = Counter()
    by_source: Counter[str] = Counter()
    seen: set[str] = set()
    source_rows = fetch_source_rows(limit_source_rows)

    for source_index, messages in enumerate(source_rows):
        if len(rows) >= limit:
            break
        if not isinstance(messages, list):
            skipped["bad_messages"] += 1
            continue
        for i, message in enumerate(messages):
            if len(rows) >= limit:
                break
            if not isinstance(message, dict) or message.get("role") != "assistant":
                continue
            parsed = parse_function_xml(str(message.get("content", "")))
            if not parsed:
                skipped["assistant_without_tool_call"] += 1
                continue
            next_observation = ""
            if i + 1 < len(messages) and isinstance(messages[i + 1], dict):
                next_observation = str(messages[i + 1].get("content", ""))
            target, source_kind = convert_tool_call(parsed[0], parsed[1], next_observation)
            if not target:
                skipped[source_kind] += 1
                continue
            try:
                validate_ultra_compact_assistant(target)
            except Exception as exc:  # pragma: no cover - defensive report path
                skipped[f"validation:{exc}"] += 1
                continue
            context = build_context(messages, i)
            if not context:
                skipped["missing_user_context"] += 1
                continue
            example = {
                "messages": [*context, {"role": "assistant", "content": target}],
                "style": STYLE_NAME,
                "source": DATASET,
                "source_split": SOURCE_SPLIT,
                "source_row": source_index,
                "source_turn": i,
                "source_conversion": source_kind,
            }
            fingerprint = json.dumps(example["messages"], ensure_ascii=False, sort_keys=True)
            if fingerprint in seen:
                skipped["duplicate"] += 1
                continue
            seen.add(fingerprint)
            rows.append(example)
            by_kind[output_kind(target)] += 1
            tool = output_tool(target)
            if tool:
                by_tool[tool] += 1
            by_source[source_kind] += 1

    report = {
        "dataset": DATASET,
        "source_split": SOURCE_SPLIT,
        "parquet_file": PARQUET_FILE,
        "usage": "uv run --with duckdb --with huggingface_hub python scripts/convert_hf_openhands_swe.py --output data/examples/hermes_hf_openhands_swe.v0.jsonl --report reports/hermes-hf-openhands-swe-quality.json --limit 300 --min-rows 100",
        "rows": len(rows),
        "source_rows_read": len(source_rows),
        "style": STYLE_NAME,
        "skipped_reasons": dict(sorted(skipped.items())),
        "by_output_kind": dict(sorted(by_kind.items())),
        "by_tool": dict(sorted(by_tool.items())),
        "by_source_conversion": dict(sorted(by_source.items())),
    }
    return rows, report


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows))


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert OpenHands/SWE-Gym success trajectories to Hermes ultra-compact JSONL.")
    parser.add_argument("--output", default="data/examples/hermes_hf_openhands_swe.v0.jsonl")
    parser.add_argument("--report", default="reports/hermes-hf-openhands-swe-quality.json")
    parser.add_argument("--limit", type=int, default=300)
    parser.add_argument("--source-row-limit", type=int, default=0, help="Optional cap on source parquet rows read before conversion.")
    parser.add_argument("--min-rows", type=int, default=100)
    args = parser.parse_args()

    rows, report = convert(args.limit, args.source_row_limit or None)
    if len(rows) < args.min_rows:
        raise SystemExit(f"only produced {len(rows)} rows, below --min-rows={args.min_rows}")
    output_path = ROOT / args.output if not Path(args.output).is_absolute() else Path(args.output)
    report_path = ROOT / args.report if not Path(args.report).is_absolute() else Path(args.report)
    write_jsonl(output_path, rows)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"output": str(output_path), "report": str(report_path), "rows": len(rows)}, indent=2))


if __name__ == "__main__":
    main()
