from __future__ import annotations
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from functools import lru_cache
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

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
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "reasoning_tokens",
    "tool_input_tokens",
    "tool_output_tokens",
    "tool_calls_input_tokens",
    "tool_calls_output_tokens",
}

# Normalisation map: synonymous keys map to a canonical key so that, e.g.,
# prompt_tokens and input_tokens both contribute to input_tokens in the final
# aggregate. Canonical names use the _input_tokens / _output_tokens suffix.
_TOKEN_NORMALIZE: dict[str, str] = {
    "prompt_tokens": "input_tokens",
    "completion_tokens": "output_tokens",
}



# Hermes CLI built-ins as of the runtime inventory used by this adapter.  Names
# outside this set must not be passed to --toolsets: Hermes silently resolves
# unknown toolsets to an empty schema, which would turn an environment/setup
# error into a bogus model failure.
_CLI_TOOLSETS = {
    "web",
    "browser",
    "terminal",
    "file",
    "code_execution",
    "vision",
    "video",
    "image_gen",
    "video_gen",
    "x_search",
    "tts",
    "skills",
    "todo",
    "memory",
    "session_search",
    "clarify",
    "delegation",
    "cronjob",
    "homeassistant",
    "spotify",
    "yuanbao",
    "computer_use",
}

_TOOLSET_MAP = {
    "web": "web",
    "browser": "browser",
    "terminal": "terminal",
    "file": "file",
    "code_execution": "code_execution",
    "vision": "vision",
    "image_gen": "image_gen",
    "video": "video",
    "video_gen": "video_gen",
    "tts": "tts",
    "skills": "skills",
    "memory": "memory",
    "session_search": "session_search",
    "semantic_search": "semantic_search",
    "clarify": "clarify",
    "delegation": "delegation",
    "cronjob": "cronjob",
    "computer_use": "computer_use",
    "todo": "todo",
    "kanban": "kanban",
    "project": "project",
    "x_search": "x_search",
    "yuanbao": "yuanbao",
    "spotify": "spotify",
    "feishu": "feishu",
    "discord": "discord",
    "discord_admin": "discord_admin",
    "stt": "stt",
    "obsidian": "obsidian",
    "github": "github",
    "docker": "docker",
    "notion": "notion",
    "linear": "linear",
    "maps": "maps",
    "himalaya": "himalaya",
    "openhue": "openhue",
    "homeassistant": "homeassistant",
    "messaging": "messaging",
    "search": "web",
    "browser_cdp": "browser_cdp",
}

# Map a capability class (as used in tool_use_requirements) to the Hermes
# toolset(s) that must be enabled for the model to use that capability.
_CAPABILITY_TOOLSETS = {
    "web": ["web"],
    "browser": ["browser", "web"],
    "browser_cdp": ["browser"],
    "terminal": ["terminal"],
    "file": ["file"],
    "code_execution": ["code_execution"],
    "vision": ["vision"],
    "image_gen": ["image_gen"],
    "video": ["video"],
    "video_gen": ["video_gen"],
    "tts": ["tts"],
    "skills": ["skills"],
    "memory": ["memory"],
    "session_search": ["session_search"],
    "semantic_search": ["semantic_search"],
    "clarify": ["clarify"],
    "delegation": ["delegation"],
    "cronjob": ["cronjob"],
    "computer_use": ["computer_use"],
    "todo": ["todo"],
    "kanban": ["kanban"],
    "project": ["project"],
    "x_search": ["x_search"],
    "yuanbao": ["yuanbao"],
    "spotify": ["spotify"],
    "feishu": ["feishu"],
    "discord": ["discord"],
    "discord_admin": ["discord_admin"],
    "stt": ["stt"],
    "obsidian": ["obsidian"],
    "github": ["github"],
    "docker": ["docker"],
    "notion": ["notion"],
    "linear": ["linear"],
    "maps": ["maps"],
    "himalaya": ["himalaya"],
    "openhue": ["openhue"],
    "homeassistant": ["homeassistant"],
    "messaging": ["messaging"],
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
            # Normalise synonymous keys (prompt_tokens → input_tokens, etc.)
            canonical = _TOKEN_NORMALIZE.get(k, k)
            dst[canonical] = dst.get(canonical, 0) + n


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
        nested_usage_parent_ids = {
            id(node)
            for node in _walk(obj)
            if isinstance(node, dict)
            and any(isinstance(node.get(key), dict) for key in _USAGE_KEYS)
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
            elif any(k in node for k in ("tool", "tool_name", "name")) and (
                "tool" in event or node.get("role") == "tool"
            ):
                event_tool_count += 1
            for key in _USAGE_KEYS:
                if isinstance(node.get(key), dict):
                    _merge_usage(usage, node[key])
            # Skip nested usage nodes and their parents' direct fields. This
            # prevents double-counting when a response repeats usage values at
            # both {"usage": {"total_tokens": 100}} and the outer level.
            if id(node) not in nested_usage_ids | nested_usage_parent_ids:
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
                canonical = _TOKEN_NORMALIZE.get(key, key)
                usage[canonical] = usage.get(canonical, 0) + (_num(m.group(1)) or 0)
    if cost is None:
        m = re.search(r"cost(?:_usd)?\s*[:=]\s*\$?(\d+(?:\.\d+)?)", text, re.I)
        if m:
            cost = float(m.group(1))

    # Hermes human-readable logs, e.g.:
    # API call #1: model=... in=7459 out=52 total=7511 latency=2.4s
    # agent.tool_executor: tool read_file completed (...)
    for m in re.finditer(
        r"API call #\d+:.*?\bin=(\d+)\s+out=(\d+)\s+total=(\d+)", text
    ):
        usage["input_tokens"] = usage.get("input_tokens", 0) + int(m.group(1))
        usage["output_tokens"] = usage.get("output_tokens", 0) + int(m.group(2))
        usage["total_tokens"] = usage.get("total_tokens", 0) + int(m.group(3))
    log_tool_count = len(
        re.findall(r"agent\.tool_executor: tool [\w.-]+ completed", text)
    )
    if log_tool_count:
        event_tool_count += log_tool_count

    telemetry.tool_calls = (
        explicit_tool_count if explicit_tool_count is not None else event_tool_count
    )
    # Compute aggregate total_tokens from input+output when total_tokens was
    # not explicitly provided (avoids double-counting an already-present total).
    if usage:
        if "total_tokens" not in usage:
            inp = usage.get("input_tokens", 0)
            out = usage.get("output_tokens", 0)
            if inp or out:
                usage["total_tokens"] = inp + out
    telemetry.token_usage = usage or None
    telemetry.cost_usd = cost
    return telemetry


def _recent_hermes_text(
    started_at: float,
    limit_files: int = 8,
    max_bytes: int = 64_000,
    session_id: str | None = None,
    profile_dir: Path | None = None,
) -> tuple[str, str | None]:
    """Read only bounded Hermes runtime files, never recursively scan venv/cache."""
    home = Path.home() / ".hermes"
    roots = [home / "logs", home / "sessions"]
    if profile_dir is not None:
        roots.extend([profile_dir / "logs", profile_dir / "sessions"])
    candidates: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        for path in root.glob("*"):
            try:
                if (
                    path.is_file()
                    and path.suffix in {".jsonl", ".json", ".log"}
                    and path.stat().st_mtime >= started_at - 2
                ):
                    candidates.append(path)
            except OSError:
                pass
    chunks = []
    chosen = sorted(set(candidates), key=lambda p: p.stat().st_mtime, reverse=True)[
        :limit_files
    ]
    for path in chosen:
        try:
            data = path.read_bytes()[-max_bytes:].decode("utf-8", errors="replace")
        except OSError:
            continue
        if session_id:
            data = "\n".join(line for line in data.splitlines() if session_id in line)
        chunks.append(data)
    return "\n".join(chunks), "hermes-session-or-log" if chunks else None


def _resolve_toolsets(task) -> list[str]:
    """Return the toolsets to grant Hermes for this task.

    Tasks declare the toolsets they expect the model to choose from. If the task
    explicitly asks for `all`, the adapter enables every built-in toolset. By
    default we still keep the benchmark local-only, so we do not auto-enable
    external-only tools unless the task explicitly asks for them.
    """
    requested = [
        str(t).lower().strip() for t in task.metadata.get("required_toolsets", []) or []
    ]
    unknown = sorted(
        {
            t or "<empty>"
            for t in requested
            if t != "all" and t not in _CAPABILITY_TOOLSETS and t not in _TOOLSET_MAP
        }
    )
    if unknown:
        raise ValueError(f"Unknown task-requested toolsets: {', '.join(unknown)}")
    if "all" in requested:
        return sorted(set(_TOOLSET_MAP.values()))
    out = []
    for t in requested:
        if t in _CAPABILITY_TOOLSETS:
            out.extend(_CAPABILITY_TOOLSETS[t])
        elif t in _TOOLSET_MAP:
            out.append(_TOOLSET_MAP[t])
    if not out:
        # Backward-compatible default for projectops tasks.
        return ["terminal", "file"]
    return sorted(set(out))


def unsupported_cli_toolsets(task, *, check_runtime: bool = True) -> list[str]:
    """Return requested toolsets that Hermes CLI cannot expose via --toolsets."""
    available = available_cli_toolsets() if check_runtime else _CLI_TOOLSETS
    return sorted(set(_resolve_toolsets(task)) - available)


@lru_cache(maxsize=1)
def available_cli_toolsets() -> set[str]:
    """Read the enabled Hermes CLI toolsets from the current installation."""
    try:
        result = subprocess.run(
            ["hermes", "tools", "list"], capture_output=True, text=True, timeout=10
        )
    except (OSError, subprocess.SubprocessError):
        return set(_CLI_TOOLSETS)
    if result.returncode != 0:
        return set(_CLI_TOOLSETS)
    enabled = set()
    for line in result.stdout.splitlines():
        match = re.search(r"✓ enabled\s+(\S+)", line)
        if match and match.group(1) in _CLI_TOOLSETS:
            enabled.add(match.group(1))
    return enabled or set(_CLI_TOOLSETS)


@dataclass
class StateDBTelemetry:
    trusted: bool = False
    session_id: str | None = None
    events: list[dict] = None
    tool_calls: int = 0
    token_usage: dict[str, int | float] | None = None
    cost_usd: float | None = None
    runtime_issues: list[str] = None


def _tool_result_succeeded(content: Any, disposition: Any) -> bool:
    """Conservatively classify a structured Hermes tool completion result."""
    if str(disposition or "").lower() in {"failed", "error", "rejected"}:
        return False
    if not isinstance(content, str) or not content.strip():
        return True
    try:
        payload = json.loads(content)
    except (TypeError, ValueError, json.JSONDecodeError):
        return not re.match(r"^\s*(?:error|failed)\b", content, re.I)
    if not isinstance(payload, dict):
        return True
    if payload.get("success") is False:
        return False
    if str(payload.get("status", "")).lower() in {"failed", "error"}:
        return False
    return not bool(payload.get("error"))


def _extract_state_db_telemetry(
    db_path: Path,
    started_at: float,
    workdir: Path,
    session_id: str | None = None,
) -> StateDBTelemetry:
    """Read trusted telemetry for one root session and its descendants."""
    import sqlite3

    result = StateDBTelemetry(events=[], runtime_issues=[])
    if not db_path.exists():
        return result
    try:
        conn = sqlite3.connect(str(db_path))
        session_schema = {
            row[1] for row in conn.execute("PRAGMA table_info(sessions)").fetchall()
        }
        message_schema = {
            row[1] for row in conn.execute("PRAGMA table_info(messages)").fetchall()
        }
        optional = [
            name if name in session_schema else f"NULL AS {name}"
            for name in ("parent_session_id", "end_reason", "handoff_error")
        ]
        session_columns = (
            "SELECT id, started_at, ended_at, tool_call_count, input_tokens, "
            "output_tokens, reasoning_tokens, estimated_cost_usd, actual_cost_usd, cwd, "
            + ", ".join(optional)
            + " FROM sessions"
        )
        if session_id:
            root_rows = conn.execute(
                f"{session_columns} WHERE id = ?", (session_id,)
            ).fetchall()
            if not root_rows:
                conn.close()
                return result
            root_id = session_id
        else:
            root_rows = conn.execute(
                f"{session_columns} WHERE started_at >= ? "
                "AND (cwd = ? OR cwd IS NULL) ORDER BY started_at",
                (started_at - 2.0, str(workdir)),
            ).fetchall()
            if "parent_session_id" in session_schema:
                root_rows = [row for row in root_rows if row[10] is None]
            if not root_rows or (
                "parent_session_id" in session_schema and len(root_rows) != 1
            ):
                conn.close()
                return result
            root_id = root_rows[0][0]

        if "parent_session_id" in session_schema:
            session_ids = [root_id]
            frontier = [root_id]
            while frontier:
                placeholders = ",".join("?" for _ in frontier)
                children = [
                    row[0]
                    for row in conn.execute(
                        f"SELECT id FROM sessions WHERE parent_session_id IN ({placeholders})",
                        frontier,
                    ).fetchall()
                    if row[0] not in session_ids
                ]
                session_ids.extend(children)
                frontier = children
            placeholders = ",".join("?" for _ in session_ids)
            rows = conn.execute(
                f"{session_columns} WHERE id IN ({placeholders}) ORDER BY started_at",
                session_ids,
            ).fetchall()
        else:
            # Old Hermes databases did not persist session lineage. The profile
            # is isolated, so retain the prior bounded CWD fallback for them.
            rows = conn.execute(
                f"{session_columns} WHERE started_at >= ? "
                "AND (id = ? OR cwd = ? OR cwd IS NULL) ORDER BY started_at",
                (root_rows[0][1] - 2.0, root_id, str(workdir)),
            ).fetchall()
        if not rows:
            conn.close()
            return result

        session_ids = [row[0] for row in rows]
        placeholders = ",".join("?" for _ in session_ids)
        content = "content" if "content" in message_schema else "NULL AS content"
        disposition = (
            "effect_disposition"
            if "effect_disposition" in message_schema
            else "NULL AS effect_disposition"
        )
        tool_call_id = "tool_call_id" if "tool_call_id" in message_schema else "NULL AS tool_call_id"
        messages = conn.execute(
            f"SELECT session_id, role, tool_name, tool_calls, timestamp, {content}, "
            f"{disposition}, {tool_call_id} FROM messages "
            f"WHERE session_id IN ({placeholders}) ORDER BY rowid",
            session_ids,
        ).fetchall()
        call_arguments: dict[str, dict] = {}
        for _sid, role, _name, tool_calls, _ts, _content, _effect, _call_id in messages:
            if role != "assistant" or not tool_calls:
                continue
            try:
                proposed_calls = json.loads(tool_calls)
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if not isinstance(proposed_calls, list):
                continue
            for call in proposed_calls:
                if not isinstance(call, dict):
                    continue
                function = call.get("function")
                call_id = call.get("id") or call.get("call_id")
                if not call_id or not isinstance(function, dict):
                    continue
                arguments = function.get("arguments")
                if isinstance(arguments, str):
                    try:
                        arguments = json.loads(arguments)
                    except (TypeError, ValueError, json.JSONDecodeError):
                        continue
                if isinstance(arguments, dict):
                    call_arguments[str(call_id)] = arguments

        for message_sid, role, tool_name, _tool_calls, timestamp, tool_content, effect, call_id in messages:
            # Hermes persists both the assistant's proposed call and the
            # resulting tool message. Only the latter proves execution.
            if role == "tool" and tool_name:
                event = {"tool_name": tool_name, "timestamp": timestamp}
                arguments = call_arguments.get(str(call_id)) if call_id else None
                if arguments is not None:
                    event["arguments"] = arguments
                if effect is not None:
                    event["effect_disposition"] = effect
                succeeded = _tool_result_succeeded(tool_content, effect)
                if not succeeded:
                    event["succeeded"] = False
                result.events.append(event)
                trusted_text = str(tool_content or "")
                if tool_name == "computer_use" and re.search(
                    r"cua_driver.*MCP server error", trusted_text, re.I | re.S
                ):
                    result.runtime_issues.append("computer_use_runtime_unavailable")
                if tool_name == "vision_analyze" and re.search(
                    r"(?:server error|failed to process|vision.*unavailable)",
                    trusted_text,
                    re.I,
                ):
                    result.runtime_issues.append("vision_runtime_unavailable")
                if tool_name == "delegate_task" and re.search(
                    r"(?:Interrupted during API call|Interrupt: skipping \d+ tool call)",
                    trusted_text,
                ):
                    result.runtime_issues.append("delegation_provider_interrupted")
                if (
                    message_sid == root_id
                    and tool_name == "delegate_task"
                    and isinstance(arguments, dict)
                    and arguments.get("background") is True
                ):
                    try:
                        delegation_result = json.loads(tool_content or "{}")
                    except (TypeError, ValueError, json.JSONDecodeError):
                        delegation_result = {}
                    if (
                        isinstance(delegation_result, dict)
                        and delegation_result.get("status") == "dispatched"
                        and delegation_result.get("mode") == "background"
                    ):
                        result.runtime_issues.append("delegation_detached_one_shot")
        for row in rows:
            parent_id, end_reason, handoff_error = row[10], row[11], row[12]
            if parent_id is not None and re.search(
                r"(?:Interrupted during API call|API.*interrupt|provider.*interrupt)",
                f"{end_reason or ''} {handoff_error or ''}",
                re.I,
            ):
                result.runtime_issues.append("delegation_provider_interrupted")
        conn.close()
        result.trusted = True
        result.session_id = root_id
        result.tool_calls = len(result.events)
        result.token_usage = {
            "input_tokens": sum(row[4] or 0 for row in rows),
            "output_tokens": sum(row[5] or 0 for row in rows),
            "reasoning_tokens": sum(row[6] or 0 for row in rows),
        }
        result.cost_usd = sum(
            (row[8] if row[8] is not None else row[7] or 0) or 0 for row in rows
        )
        result.runtime_issues = sorted(set(result.runtime_issues))
        return result
    except (OSError, sqlite3.Error):
        return result


def _tool_log_lines(profile_dir: Path | None, session_id: str | None = None) -> str:
    """Extract tool completion records from a Hermes profile directory.

    The CLI runs in -Q quiet mode, so stdout only contains the final response.
    Tool execution evidence is stored in the profile's state DB. We query the
    messages table for the current session and append synthetic log lines so the
    behavior grader can map observed tool names to capability classes.
    """
    if profile_dir is None:
        return ""
    logs: list[str] = []
    db_path = profile_dir / "state.db"
    if db_path.exists():
        try:
            import sqlite3

            conn = sqlite3.connect(str(db_path))
            if session_id:
                rows = conn.execute(
                    "SELECT tool_name FROM messages WHERE session_id = ? AND role = 'tool' AND tool_name IS NOT NULL",
                    (session_id,),
                ).fetchall()
            else:
                rows = []
            for (tool_name,) in rows:
                logs.append(
                    f"agent.tool_executor: tool {tool_name} completed (from_state_db)"
                )
            conn.close()
        except Exception:
            pass
    return "\n".join(logs)


def _marked_session_id(text: str, run_marker: str) -> str | None:
    """Accept a state-db session only when CLI output binds it to this run."""
    for obj in _json_objects(text):
        if obj.get("hermesbench_run_marker") != run_marker:
            continue
        session_id = obj.get("session_id")
        if isinstance(session_id, str) and re.fullmatch(r"[\w-]+", session_id):
            return session_id
    return None


def _profile_with_cwd(
    profile: str | None,
    workdir: Path,
    reasoning_effort: str | None = None,
    provider: str | None = None,
    model: str | None = None,
) -> tuple[str, Path]:
    """Create a temporary profile that overrides terminal.cwd to workdir.

    Hermes tools use the configured terminal.cwd, not the subprocess cwd. Without
    this override file/terminal/search tools operate in the wrong directory and
    benchmark tasks fail. When ``reasoning_effort`` is omitted, the source
    profile's configured value is intentionally inherited; otherwise the
    temporary profile overrides it.
    """
    home = Path.home() / ".hermes"
    profiles_dir = home / "profiles"
    name = profile or "hermesbench"
    src = profiles_dir / name
    if not src.is_dir():
        raise ValueError(
            f"Hermes profile {name!r} not found at {src}.\n"
            f"Create it with: hermes profile create {name} --clone --no-alias\n"
            f"Then edit {src}/config.yaml (or pass --provider/--model per run)\n"
            "to select the local or cloud provider/model."
        )
    tmp_name = f"hermesbench-{uuid.uuid4().hex[:12].lower()}"
    dst = profiles_dir / tmp_name
    try:
        # Carry profile configuration, authentication, plugins, and skills forward, but
        # never seed a benchmark task with another agent session, memory, cache, or
        # telemetry. Apart from contaminating behavior grading, copied state can let a
        # task access unrelated user context.
        shutil.copytree(
            src,
            dst,
            ignore=shutil.ignore_patterns(
                "state.db*",
                "memory_store.db*",
                "verification_evidence.db*",
                "semantic_index.sqlite*",
                "projects.db*",
                "logs",
                "sessions",
                "runtime",
                "memories",
                "cron",
                "cache",
                "models_dev_cache.json",
                ".update_check",
                ".skills_prompt_snapshot.json",
            ),
        )
        cfg = dst / "config.yaml"
        data = yaml.safe_load(cfg.read_text()) if cfg.exists() else {}
        data = data if isinstance(data, dict) else {}
        terminal = data.setdefault("terminal", {})
        if not isinstance(terminal, dict):
            terminal = data["terminal"] = {}
        # Hermes tools honor terminal.cwd rather than the launcher cwd.
        terminal["cwd"] = str(workdir.resolve())
        # Do not carry a stale user-browser websocket URL into an isolated
        # benchmark run. Empty lets Hermes use normal browser discovery.
        browser = data.setdefault("browser", {})
        if not isinstance(browser, dict):
            browser = data["browser"] = {}
        browser["cdp_url"] = ""

        # Pin benchmark children to the same provider/model as the parent
        # instead of routing them through a user's unrelated global provider.
        delegation = data.setdefault("delegation", {})
        if not isinstance(delegation, dict):
            delegation = data["delegation"] = {}
        delegation["provider"] = provider or ""
        delegation["model"] = model or ""
        for key in ("base_url", "api_key", "api_mode"):
            delegation[key] = ""

        if reasoning_effort is not None:
            agent = data.setdefault("agent", {})
            if not isinstance(agent, dict):
                agent = data["agent"] = {}
            agent["reasoning_effort"] = reasoning_effort
        cfg.write_text(yaml.safe_dump(data, sort_keys=False))
        return tmp_name, dst
    except Exception:
        shutil.rmtree(dst, ignore_errors=True)
        raise


def _profile_progress_token(state_db: Path) -> tuple[int, ...] | None:
    """Return a cheap progress marker for an isolated Hermes state database.

    SQLite may keep active writes in the WAL while the main database file's
    mtime and size remain unchanged. Track the WAL, but not the shared-memory
    index: SQLite updates ``-shm`` during reads and lock churn even when no
    durable agent progress has occurred, which can mask a real stall forever.
    """
    token: list[int] = []
    for path in (
        state_db,
        state_db.with_name(state_db.name + "-wal"),
    ):
        try:
            stat = path.stat()
        except OSError:
            token.extend((0, 0))
        else:
            token.extend((stat.st_mtime_ns, stat.st_size))
    return tuple(token)


def _transcript_runtime_issues(transcript: str) -> list[str]:
    """Classify provider failures emitted by the trusted Hermes CLI process."""
    if re.search(r"HTTP\s+403:\s*Key limit exceeded", transcript, re.I):
        return ["provider_key_limit_exceeded"]
    return []


def _run_with_stall_detection(
    cmd: list[str],
    workdir: Path,
    state_db: Path,
    stall_idle_seconds: float | None,
) -> tuple[subprocess.CompletedProcess[str], bool]:
    """Run Hermes with an optional idle-progress guard, not a task timeout."""
    # ``chat -q`` is a request/response process: it has no live channel to
    # receive Hermes' later async-delegation completion event. Tell Hermes to
    # use its synchronous fallback for background=true delegation, which still
    # runs batch children in parallel but keeps the result in this response.
    env = os.environ.copy()
    env["HERMES_SESSION_ASYNC_DELIVERY"] = "0"
    process = subprocess.Popen(
        cmd,
        cwd=workdir,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if stall_idle_seconds is None:
        stdout, stderr = process.communicate()
        return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr), False

    last_token = _profile_progress_token(state_db)
    last_progress = time.monotonic()
    poll_seconds = min(0.25, max(0.01, stall_idle_seconds / 4))
    while True:
        try:
            stdout, stderr = process.communicate(timeout=poll_seconds)
            return subprocess.CompletedProcess(cmd, process.returncode, stdout, stderr), False
        except subprocess.TimeoutExpired:
            token = _profile_progress_token(state_db)
            now = time.monotonic()
            if token != last_token:
                last_token = token
                last_progress = now
            elif now - last_progress >= stall_idle_seconds:
                process.terminate()
                try:
                    stdout, stderr = process.communicate(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    stdout, stderr = process.communicate()
                return subprocess.CompletedProcess(
                    cmd, process.returncode, stdout, stderr
                ), True


class HermesCLIAdapter(AgentAdapter):
    def __init__(
        self,
        model: str | None = None,
        provider: str | None = None,
        reasoning_effort: str | None = None,
        profile: str | None = None,
        stall_idle_seconds: float | None = 300.0,
    ):
        super().__init__(model, provider=provider, reasoning_effort=reasoning_effort)
        self.profile = profile
        self.stall_idle_seconds = stall_idle_seconds

    def run_task(self, task, workdir: Path, hidden_dir: Path | None = None) -> AgentRun:
        toolsets = _resolve_toolsets(task)
        unsupported = sorted(set(toolsets) - _CLI_TOOLSETS)
        if unsupported:
            raise ValueError(f"CLI-unavailable toolsets: {', '.join(unsupported)}")
        expected = task.metadata.get("expected_artifacts") or []
        artifacts_hint = ""
        if expected:
            artifacts_hint = (
                "\n\nREQUIRED ARTIFACTS — you must create these files with the write_file tool: "
                + ", ".join(str(a) for a in expected)
                + ". "
                "Do not put the answer only in your response text; the final text response is not graded. "
                "If the task asks for a final answer, write it into the artifact file(s) instead of (or in addition to) the response text."
            )
        prompt = (
            f"HermesBench task {task.metadata['id']}\n\n"
            f"{task.prompt}\n\n"
            f"Workdir: {workdir}. Use the tools available to you to complete this task. "
            "You are expected to choose the right tools and features naturally, not to rely on the final answer text alone."
            f"{artifacts_hint}\n\n"
            "Important: the file/terminal/search tools operate inside the Workdir above. "
            "Always use paths relative to the Workdir, not system paths found by search."
        )
        if "delegation" in toolsets:
            prompt += (
                "\n\nThis is a one-shot benchmark process with no later turn available. "
                "If you use delegate_task, call it with background=false so the "
                "delegated results are returned in this turn. After the delegation "
                "result returns, complete all remaining parent-side work and verify "
                "the required artifacts before your final response."
            )
        cmd = ["hermes"]
        tmp_profile_dir: Path | None = None
        try:
            started_at = __import__("time").time()
            profile_name, tmp_profile_dir = _profile_with_cwd(
                self.profile,
                workdir,
                reasoning_effort=self.reasoning_effort,
                provider=self.provider,
                model=self.model,
            )
            cmd += ["-p", profile_name]
            cmd += [
                "chat",
                "-q",
                prompt,
                "-Q",
                "--toolsets",
                ",".join(toolsets),
            ]
            if getattr(self, "provider", None):
                cmd += ["--provider", self.provider]
            if self.model:
                cmd += ["--model", self.model]
            p, stalled = _run_with_stall_detection(
                cmd,
                workdir,
                tmp_profile_dir / "state.db",
                self.stall_idle_seconds,
            )
            transcript = p.stdout + p.stderr
            cli_session_match = re.search(
                r"(?:^|\n)session_id:\s*([\w-]+)", transcript
            )
            cli_session_id = (
                cli_session_match.group(1) if cli_session_match else None
            )
            telemetry = (
                _extract_state_db_telemetry(
                    tmp_profile_dir / "state.db",
                    started_at=started_at,
                    workdir=workdir,
                    session_id=cli_session_id,
                )
                if tmp_profile_dir is not None
                else StateDBTelemetry(events=[], runtime_issues=[])
            )
            runtime_issues = sorted(
                set(telemetry.runtime_issues + _transcript_runtime_issues(transcript))
            )
            return AgentRun(
                "stalled" if stalled else ("completed" if p.returncode == 0 else "failed"),
                transcript,
                telemetry.tool_calls,
                telemetry.cost_usd,
                bool(
                    p.returncode == 0
                    and re.search(r"\b(done|completed|finished)\b", transcript, re.I)
                ),
                telemetry.token_usage,
                "profile-state-db" if telemetry.trusted else None,
                tool_events=telemetry.events,
                behavior_evidence_trusted=telemetry.trusted,
                stalled=stalled,
                runtime_issues=runtime_issues,
            )
        finally:
            if tmp_profile_dir is not None:
                shutil.rmtree(tmp_profile_dir, ignore_errors=True)
