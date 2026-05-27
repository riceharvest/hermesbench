#!/usr/bin/env python3
"""Convert OpenThoughts terminal-agent traces into Hermes ultra-compact JSONL.

The converter is intentionally conservative:
- keeps only compact ACTION terminal rows by default;
- strips OpenThoughts analysis/plan fields completely;
- rejects risky, placeholder, secret-looking, or non-shell wait rows;
- validates every assistant target with validate_ultra_compact_assistant.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
import types
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

try:
    import duckdb  # type: ignore
except ImportError as exc:  # pragma: no cover - runtime dependency check
    raise SystemExit("duckdb is required: python -m pip install duckdb") from exc


def _load_ultra_compact_symbols() -> tuple[str, Any, Any]:
    """Load ultra_compact.py without importing package __init__ (which needs torch)."""
    package = types.ModuleType("qwen_mtp_probe")
    package.__path__ = [str(SRC / "qwen_mtp_probe")]  # type: ignore[attr-defined]
    sys.modules.setdefault("qwen_mtp_probe", package)

    datasets_spec = importlib.util.spec_from_file_location(
        "qwen_mtp_probe.datasets", SRC / "qwen_mtp_probe" / "datasets.py"
    )
    if datasets_spec is None or datasets_spec.loader is None:
        raise RuntimeError("could not load qwen_mtp_probe.datasets")
    datasets_mod = importlib.util.module_from_spec(datasets_spec)
    sys.modules["qwen_mtp_probe.datasets"] = datasets_mod
    datasets_spec.loader.exec_module(datasets_mod)

    ultra_spec = importlib.util.spec_from_file_location(
        "qwen_mtp_probe.ultra_compact", SRC / "qwen_mtp_probe" / "ultra_compact.py"
    )
    if ultra_spec is None or ultra_spec.loader is None:
        raise RuntimeError("could not load qwen_mtp_probe.ultra_compact")
    ultra_mod = importlib.util.module_from_spec(ultra_spec)
    sys.modules["qwen_mtp_probe.ultra_compact"] = ultra_mod
    ultra_spec.loader.exec_module(ultra_mod)
    return (
        ultra_mod.STYLE_NAME,
        ultra_mod.summarize_ultra_compact_dataset,
        ultra_mod.validate_ultra_compact_assistant,
    )


STYLE_NAME, summarize_ultra_compact_dataset, validate_ultra_compact_assistant = _load_ultra_compact_symbols()

DATASET = "open-thoughts/OpenThoughts-Agent-v1-SFT"
PARQUET_URL = (
    "https://huggingface.co/datasets/"
    "open-thoughts/OpenThoughts-Agent-v1-SFT/resolve/main/data/train-00000-of-00001.parquet"
)
SYSTEM = "You are Hermes Agent. Use ultra-compact terminal actions. No hidden reasoning."
DEFAULT_OUTPUT = ROOT / "data/examples/hermes_hf_openthoughts_terminal.v0.jsonl"
DEFAULT_REPORT = ROOT / "reports/hermes-hf-openthoughts-terminal-quality.json"

SECRET_RE = re.compile(
    r"(?is)(-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----|"
    r"\b(?:api[_-]?key|secret[_-]?key|access[_-]?token|auth[_-]?token|bearer)\b\s*[:=]|"
    r"\b[A-Za-z0-9_]{0,12}(?:ghp|gho|github_pat|sk-[A-Za-z0-9])[A-Za-z0-9_\-]{16,})"
)
PLACEHOLDER_RE = re.compile(r"(?i)(<[^>]+>|\{\{[^}]+\}\}|\b(?:TODO|YOUR_|REPLACE_ME|PLACEHOLDER)\b)")
RISKY_RE = re.compile(
    r"(?ix)("
    # Teach safe shell discipline: do not positively train recursive force deletes, even
    # when the source task claims a sandboxed /workspace. They transfer badly to agents.
    r"\brm\b|"
    r"\bfind\b[^\n]*(?:-delete|-exec\s+rm\b|xargs\s+rm\b)|"
    r"\b(?:mkfs|fdisk|dd|chmod)\b|"
    r"\bchown\s+-R\b|"
    r"/etc/(?:shadow|sudoers)|"
    r"\b(?:env|printenv)\b\s*(?:[;&|]|$)|"
    r"\bcat\s+[^\n;|&]*(?:\.env|id_rsa|id_ed25519|credentials|token|secret)"
    r")"
)
RISKY_TASK_RE = re.compile(
    r"(?ix)("
    r"recursively\s+remove|"
    r"remove\s+every\s+(?:file|directory)|"
    r"delete\s+every\s+(?:file|directory)|"
    r"print\s+their\s+paths,?\s+and\s+remove\s+them|"
    r"\bremove\s+them\b|"
    r"\brm\b|"
    r"\bfind\b[^\n]*(?:-delete|-exec\s+rm\b|xargs\s+rm\b)"
    r")"
)
INTERACTIVE_RE = re.compile(r"(?ix)^\s*(?:vim|vi|nano|emacs|less|more|man|top|htop|ssh|sudo\b|su\b|passwd\b)")
PROMPT_ONLY_RE = re.compile(r"^\s*(?:#.*)?$")


def _balanced_json_object(text: str) -> dict[str, Any] | None:
    """Return the first parseable balanced JSON object embedded in text."""
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", text):
        try:
            obj, _ = decoder.raw_decode(text[match.start() :])
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _task_text(user_content: str) -> str:
    text = user_content.strip()
    if "Task Description:" in text:
        text = text.split("Task Description:", 1)[1]
    for marker in ("Current terminal state:", "Current Terminal Screen:"):
        if marker in text:
            text = text.split(marker, 1)[0]
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text[:3000]


def _observation_text(user_content: str) -> str:
    text = user_content.strip()
    # Remove source harness grading prompt; keep terminal observations only.
    text = re.split(r"\nAre you sure you want to mark the task as complete\?", text, maxsplit=1)[0]
    # Keep observations compact but grounded; drop repeated blank terminal padding.
    text = re.sub(r"\n{4,}", "\n\n", text)
    if len(text) > 3500:
        text = text[-3500:]
        first_nl = text.find("\n")
        if first_nl > 0:
            text = text[first_nl + 1 :]
        text = "Previous terminal output (tail):\n" + text
    return text


def _normalize_command(keystrokes: Any) -> str:
    if not isinstance(keystrokes, str):
        return ""
    cmd = keystrokes.replace("\r\n", "\n").replace("\r", "\n")
    # Source keystrokes include the Enter key as a final newline. Remove only outer whitespace.
    return cmd.strip()


def _command_skip_reason(cmd: str) -> str | None:
    if not cmd or PROMPT_ONLY_RE.match(cmd):
        return "empty_or_wait_command"
    if len(cmd) > 1000:
        return "command_too_long"
    if "\x00" in cmd:
        return "nul_in_command"
    if SECRET_RE.search(cmd):
        return "secret_like_command"
    if PLACEHOLDER_RE.search(cmd):
        return "placeholder_command"
    if RISKY_RE.search(cmd):
        return "risky_command"
    if INTERACTIVE_RE.search(cmd):
        return "interactive_command"
    # Reject copied prompts or shell transcripts rather than commands.
    if re.search(r"(?m)^\w+@[^\n]+#\s", cmd):
        return "terminal_transcript_command"
    return None


def _timeout_for(command: str, duration: Any) -> int | None:
    timeout = None
    if isinstance(duration, (int, float)) and duration >= 5:
        timeout = min(120, max(10, int(duration) + 5))
    if re.search(r"\b(pip|pytest|npm|make|cmake|curl|wget|git\s+clone|python\s+-m)\b", command):
        timeout = max(timeout or 0, 120)
    elif re.search(r"\b(find|grep|tar|gzip|unzip)\b", command):
        timeout = max(timeout or 0, 30)
    return timeout or None


def _action_content(command: str, duration: Any) -> str:
    payload: dict[str, Any] = {"command": command}
    # OpenThoughts terminal tasks run from /workspace; include it when the command is path-sensitive.
    if re.search(r"(^|[\s;&|])(\.|/workspace|find|ls|pwd|cat|mkdir|python|pytest|grep|sed|awk)\b", command):
        payload["workdir"] = "/workspace"
    timeout = _timeout_for(command, duration)
    if timeout is not None:
        payload["timeout"] = timeout
    return "ACTION terminal " + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _assistant_kind(content: str) -> str:
    if content.startswith("ACTION "):
        return "action_only"
    if content.startswith("FINAL:"):
        return "final_only"
    if content.startswith("SCRATCH<=32:"):
        return "scratch"
    return "invalid"


def _fingerprint(messages: list[dict[str, str]]) -> str:
    blob = json.dumps(messages, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _iter_source_rows(limit_source_rows: int) -> Iterable[dict[str, Any]]:
    con = duckdb.connect(database=":memory:")
    query = "select conversations, task, episode, run_id, trial_name from read_parquet(?) limit ?"
    for conversations, task, episode, run_id, trial_name in con.execute(query, [PARQUET_URL, limit_source_rows]).fetchall():
        yield {
            "conversations": conversations,
            "task": task,
            "episode": episode,
            "run_id": run_id,
            "trial_name": trial_name,
        }


def convert(limit: int, source_limit: int) -> tuple[list[dict[str, Any]], Counter[str]]:
    rows: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    seen: set[str] = set()

    for source_index, source in enumerate(_iter_source_rows(source_limit), 1):
        conversations = source.get("conversations")
        if not isinstance(conversations, list) or len(conversations) < 2:
            skipped["bad_conversation"] += 1
            continue

        initial_user = next((m for m in conversations if isinstance(m, dict) and m.get("role") == "user"), None)
        task = _task_text(str(initial_user.get("content", ""))) if initial_user else ""
        if SECRET_RE.search(task):
            skipped["secret_like_user"] += 1
            continue
        if RISKY_TASK_RE.search(task):
            skipped["risky_task"] += 1
            continue

        previous_user = ""
        for turn_index, msg in enumerate(conversations):
            if not isinstance(msg, dict):
                skipped["bad_message"] += 1
                continue
            role = msg.get("role")
            content = str(msg.get("content", ""))
            if role == "user":
                previous_user = _task_text(content) if turn_index == 0 else _observation_text(content)
                if RISKY_RE.search(previous_user) or RISKY_TASK_RE.search(previous_user):
                    skipped["risky_user_context"] += 1
                    previous_user = ""
                continue
            if role != "assistant":
                continue
            if not previous_user:
                skipped["assistant_without_user"] += 1
                continue
            if re.search(r"Missing required fields: analysis, plan, commands|proper JSON response", previous_user):
                skipped["source_harness_repair_prompt"] += 1
                continue
            if SECRET_RE.search(content):
                skipped["secret_like_assistant"] += 1
                continue

            source_json = _balanced_json_object(content)
            if source_json is None:
                skipped["assistant_not_json"] += 1
                continue
            commands = source_json.get("commands")
            if not isinstance(commands, list) or not commands:
                skipped["no_commands"] += 1
                continue

            for command_index, command_obj in enumerate(commands):
                if not isinstance(command_obj, dict):
                    skipped["bad_command_object"] += 1
                    continue
                command = _normalize_command(command_obj.get("keystrokes"))
                reason = _command_skip_reason(command)
                if reason:
                    skipped[reason] += 1
                    continue

                assistant = _action_content(command, command_obj.get("duration"))
                try:
                    validate_ultra_compact_assistant(assistant)
                    # Also enforce that ACTION payload is parseable JSON.
                    json.loads(assistant.split(" ", 2)[2])
                except Exception as exc:  # noqa: BLE001 - report validation cause
                    skipped[f"validation:{type(exc).__name__}"] += 1
                    continue

                messages = [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": previous_user},
                    {"role": "assistant", "content": assistant},
                ]
                fp = _fingerprint(messages)
                if fp in seen:
                    skipped["duplicate"] += 1
                    continue
                seen.add(fp)
                rows.append(
                    {
                        "messages": messages,
                        "style": STYLE_NAME,
                        "source": DATASET,
                        "source_id": f"{source.get('trial_name') or source.get('run_id')}:turn{turn_index}:cmd{command_index}",
                        "tags": ["hf", "openthoughts", "terminal", _assistant_kind(assistant)],
                    }
                )
                if len(rows) >= limit:
                    return rows, skipped

    return rows, skipped


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def write_report(path: Path, rows: list[dict[str, Any]], skipped: Counter[str], source_limit: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarize_ultra_compact_dataset(rows)
    report = {
        "dataset": DATASET,
        "source_parquet": PARQUET_URL,
        "source_rows_scanned_limit": source_limit,
        "row_count": len(rows),
        "skipped_reasons": dict(sorted(skipped.items())),
        "by_output_kind": summary["by_output_kind"],
        "by_tool": summary["by_tool"],
        "by_style": summary["by_style"],
        "invalid_examples": summary.get("invalid_examples", []),
    }
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=300, help="maximum converted rows")
    parser.add_argument("--source-limit", type=int, default=1500, help="source parquet rows to scan")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    rows, skipped = convert(limit=args.limit, source_limit=args.source_limit)
    if len(rows) < min(100, args.limit):
        raise SystemExit(f"only produced {len(rows)} validated rows; skipped={dict(skipped)}")
    write_jsonl(args.output, rows)
    write_report(args.report, rows, skipped, args.source_limit)
    print(f"wrote {len(rows)} rows to {args.output}")
    print(f"wrote report to {args.report}")


if __name__ == "__main__":
    main()
