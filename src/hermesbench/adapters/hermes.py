from __future__ import annotations

import json
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .base import AgentAdapter, AgentRun


@dataclass
class HermesTelemetry:
    tool_calls: int = 0
    token_usage: dict[str, int | float] | None = None
    cost_usd: float | None = None
    source: str | None = None


_TOOL_COUNT_KEYS = ("tool_call_count", "tool_calls", "toolCallCount")
_USAGE_KEYS = ("usage", "token_usage", "tokenUsage")
_COST_KEYS = ("cost_usd", "costUSD", "cost")
_TOKEN_KEYS = {
    "prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens",
    "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens",
}


def _json_objects(text: str):
    for line in text.splitlines():
        s = line.strip()
        if not (s.startswith("{") and s.endswith("}")):
            continue
        try:
            yield json.loads(s)
        except json.JSONDecodeError:
            continue


def _walk(obj: Any):
    yield obj
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _walk(v)


def _num(v: Any) -> int | float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    if isinstance(v, str):
        try:
            return float(v) if "." in v else int(v)
        except ValueError:
            return None
    return None


def _merge_usage(dst: dict[str, int | float], usage: dict[str, Any]) -> None:
    for k, v in usage.items():
        n = _num(v)
        if n is not None and ("token" in k or k in _TOKEN_KEYS):
            dst[k] = dst.get(k, 0) + n


def extract_hermes_telemetry(text: str, source: str | None = None) -> HermesTelemetry:
    """Best-effort telemetry extraction from Hermes stdout/session/log snippets.

    Only numeric aggregate telemetry is returned; raw session/log content is never
    included in benchmark results.
    """
    telemetry = HermesTelemetry(source=source)
    usage: dict[str, int | float] = {}
    explicit_tool_count: int | None = None
    event_tool_count = 0
    cost: float | None = None

    for obj in _json_objects(text):
        nested_usage_ids = {
            id(node[key])
            for node in _walk(obj)
            if isinstance(node, dict)
            for key in _USAGE_KEYS
            if isinstance(node.get(key), dict)
        }
        for node in _walk(obj):
            if not isinstance(node, dict):
                continue
            for key in _TOOL_COUNT_KEYS:
                if key in node:
                    n = _num(node[key])
                    if n is not None:
                        explicit_tool_count = max(explicit_tool_count or 0, int(n))
            event = str(node.get("event") or node.get("type") or "").lower()
            if "tool_call" in event or event in {"tool.call", "tool-call"}:
                event_tool_count += 1
            elif any(k in node for k in ("tool", "tool_name", "name")) and ("tool" in event or node.get("role") == "tool"):
                event_tool_count += 1
            for key in _USAGE_KEYS:
                if isinstance(node.get(key), dict):
                    _merge_usage(usage, node[key])
            # Some providers put token fields directly on the response object.
            if id(node) not in nested_usage_ids:
                _merge_usage(usage, node)
            for key in _COST_KEYS:
                if key in node:
                    n = _num(node[key])
                    if n is not None:
                        cost = (cost or 0.0) + float(n) if key != "cost" else float(n)

    # Human-readable summaries seen in CLI/log output.
    if explicit_tool_count is None:
        m = re.search(r"tool(?:[_ -]?call)?s?\s*[:=]\s*(\d+)", text, re.I)
        if m:
            explicit_tool_count = int(m.group(1))
    if not usage:
        for key in _TOKEN_KEYS:
            m = re.search(rf"{re.escape(key)}\s*[:=]\s*(\d+(?:\.\d+)?)", text, re.I)
            if m:
                usage[key] = usage.get(key, 0) + (_num(m.group(1)) or 0)
    if cost is None:
        m = re.search(r"cost(?:_usd)?\s*[:=]\s*\$?(\d+(?:\.\d+)?)", text, re.I)
        if m:
            cost = float(m.group(1))

    # Hermes human-readable logs, e.g.:
    # API call #1: model=... in=7459 out=52 total=7511 latency=2.4s
    # agent.tool_executor: tool read_file completed (...)
    for m in re.finditer(r"API call #\d+:.*?\bin=(\d+)\s+out=(\d+)\s+total=(\d+)", text):
        usage["input_tokens"] = usage.get("input_tokens", 0) + int(m.group(1))
        usage["output_tokens"] = usage.get("output_tokens", 0) + int(m.group(2))
        usage["total_tokens"] = usage.get("total_tokens", 0) + int(m.group(3))
    log_tool_count = len(re.findall(r"agent\.tool_executor: tool [\w.-]+ completed", text))
    if log_tool_count:
        event_tool_count += log_tool_count

    telemetry.tool_calls = explicit_tool_count if explicit_tool_count is not None else event_tool_count
    telemetry.token_usage = usage or None
    telemetry.cost_usd = cost
    return telemetry


def _recent_hermes_text(started_at: float, limit_files: int = 8, max_bytes: int = 64_000, session_id: str | None = None) -> tuple[str, str | None]:
    """Read only bounded Hermes runtime files, never recursively scan venv/cache."""
    home = Path.home() / ".hermes"
    roots = [home / "logs", home / "sessions"]
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.glob("*"):
            try:
                if path.is_file() and path.suffix in {".jsonl", ".json", ".log"} and path.stat().st_mtime >= started_at - 2:
                    candidates.append(path)
            except OSError:
                pass
    chunks = []
    chosen = sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True)[:limit_files]
    for path in chosen:
        try:
            data = path.read_bytes()[-max_bytes:].decode("utf-8", errors="replace")
        except OSError:
            continue
        if session_id:
            data = "\n".join(line for line in data.splitlines() if session_id in line)
        chunks.append(data)
    return "\n".join(chunks), "hermes-session-or-log" if chunks else None


class HermesCLIAdapter(AgentAdapter):
    def run_task(self, task, workdir: Path) -> AgentRun:
        prompt=f"HermesBench task {task.metadata['id']}\n\n{task.prompt}\n\nWorkdir: {workdir}. Produce expected artifacts: {', '.join(task.expected_artifacts)}. Verify before final."
        cmd=['hermes','chat','-q',prompt,'-Q','--toolsets','terminal,file,web,browser']
        if getattr(self, 'provider', None): cmd += ['--provider', self.provider]
        if self.model: cmd += ['--model', self.model]
        # Hermes exposes reasoning effort through config, not a chat CLI flag.
        # The benchmark still records it in result metadata; callers should set
        # `hermes config set agent.reasoning_effort <level>` before long runs.
        started_at = time.time()
        p=subprocess.run(cmd, cwd=workdir, text=True, capture_output=True, timeout=int(task.metadata['timeout_seconds']))
        transcript = p.stdout + p.stderr
        telemetry = extract_hermes_telemetry(transcript, "stdout/stderr")
        if not (telemetry.tool_calls or telemetry.token_usage or telemetry.cost_usd is not None):
            m = re.search(r"session_id:\s*([\w-]+)", transcript)
            recent_text, recent_source = _recent_hermes_text(started_at, session_id=m.group(1) if m else None)
            if recent_text:
                telemetry = extract_hermes_telemetry(recent_text, recent_source)
        return AgentRun('completed' if p.returncode==0 else 'failed', transcript, telemetry.tool_calls, telemetry.cost_usd, True, telemetry.token_usage, telemetry.source)
