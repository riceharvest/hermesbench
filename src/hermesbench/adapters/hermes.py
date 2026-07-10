from __future__ import annotations
import json, re, shutil, subprocess, uuid
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
    "prompt_tokens", "completion_tokens", "total_tokens", "input_tokens", "output_tokens",
    "cache_read_input_tokens", "cache_creation_input_tokens", "reasoning_tokens",
}


# Hermes CLI built-ins as of the runtime inventory used by this adapter.  Names
# outside this set must not be passed to --toolsets: Hermes silently resolves
# unknown toolsets to an empty schema, which would turn an environment/setup
# error into a bogus model failure.
_CLI_TOOLSETS = {
    "web", "browser", "terminal", "file", "code_execution", "vision", "video",
    "image_gen", "video_gen", "x_search", "tts", "skills", "todo", "memory",
    "session_search", "clarify", "delegation", "cronjob", "homeassistant",
    "spotify", "yuanbao", "computer_use",
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


def _recent_hermes_text(started_at: float, limit_files: int = 8, max_bytes: int = 64_000, session_id: str | None = None, profile_dir: Path | None = None) -> tuple[str, str | None]:
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


def _resolve_toolsets(task) -> list[str]:
    """Return the toolsets to grant Hermes for this task.

    Tasks declare the toolsets they expect the model to choose from. If the task
    explicitly asks for `all`, the adapter enables every built-in toolset. By
    default we still keep the benchmark local-only, so we do not auto-enable
    external-only tools unless the task explicitly asks for them.
    """
    requested = [str(t).lower().strip() for t in task.metadata.get("required_toolsets", []) or []]
    unknown = sorted({t or "<empty>" for t in requested if t != "all" and t not in _CAPABILITY_TOOLSETS and t not in _TOOLSET_MAP})
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


def unsupported_cli_toolsets(task) -> list[str]:
    """Return requested toolsets that Hermes CLI cannot expose via --toolsets."""
    return sorted(set(_resolve_toolsets(task)) - _CLI_TOOLSETS)


@dataclass
class StateDBTelemetry:
    trusted: bool = False
    session_id: str | None = None
    events: list[dict] = None
    tool_calls: int = 0
    token_usage: dict[str, int | float] | None = None
    cost_usd: float | None = None


def _extract_state_db_telemetry(db_path: Path, started_at: float, workdir: Path) -> StateDBTelemetry:
    """Read structured telemetry from the isolated Hermes session database.

    The temporary profile is empty before launch, so a session selected by its
    creation time and configured cwd is agent-owned evidence, not model output.
    Ambiguous matches fail closed.
    """
    import sqlite3
    result = StateDBTelemetry(events=[])
    if not db_path.exists():
        return result
    try:
        conn = sqlite3.connect(str(db_path))
        rows = conn.execute(
            "SELECT id, started_at, ended_at, tool_call_count, input_tokens, output_tokens, reasoning_tokens, estimated_cost_usd, actual_cost_usd, cwd "
            "FROM sessions WHERE started_at >= ? ORDER BY started_at DESC",
            (started_at - 2.0,),
        ).fetchall()
        if len(rows) != 1:
            conn.close()
            return result
        session_id, *_ = rows[0]
        row = rows[0]
        messages = conn.execute(
            "SELECT role, tool_name, tool_calls, timestamp FROM messages WHERE session_id = ? ORDER BY rowid",
            (session_id,),
        ).fetchall()
        for role, tool_name, tool_calls, timestamp in messages:
            if role == "tool" and tool_name:
                result.events.append({"tool_name": tool_name, "timestamp": timestamp})
            elif tool_calls:
                try:
                    decoded = json.loads(tool_calls) if isinstance(tool_calls, str) else tool_calls
                    calls = decoded if isinstance(decoded, list) else [decoded]
                    for call in calls:
                        name = call.get("function", {}).get("name") if isinstance(call, dict) else None
                        if name:
                            result.events.append({"tool_name": name, "timestamp": timestamp})
                except (TypeError, ValueError, json.JSONDecodeError):
                    pass
        conn.close()
        result.trusted = True
        result.session_id = session_id
        result.tool_calls = len(result.events)
        result.token_usage = {"input_tokens": row[4], "output_tokens": row[5], "reasoning_tokens": row[6]}
        result.cost_usd = row[8] if row[8] is not None else row[7]
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
                logs.append(f"agent.tool_executor: tool {tool_name} completed (from_state_db)")
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


def _profile_with_cwd(profile: str | None, workdir: Path) -> tuple[str, Path]:
    """Create a temporary profile that overrides terminal.cwd to workdir.

    Hermes tools use the configured terminal.cwd, not the subprocess cwd. Without
    this override file/terminal/search tools operate in the wrong directory and
    benchmark tasks fail.
    """
    home = Path.home() / ".hermes"
    profiles_dir = home / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    src = profiles_dir / profile if profile else None
    tmp_name = f"hermesbench-{uuid.uuid4().hex[:12].lower()}"
    dst = profiles_dir / tmp_name
    try:
        # Carry profile configuration, authentication, plugins, and skills forward, but
        # never seed a benchmark task with another agent session, memory, cache, or
        # telemetry. Apart from contaminating behavior grading, copied state can let a
        # task access unrelated user context.
        if src is not None and src.is_dir():
            shutil.copytree(
                src,
                dst,
                ignore=shutil.ignore_patterns(
                    "state.db*", "memory_store.db*", "verification_evidence.db*",
                    "semantic_index.sqlite*", "projects.db*", "logs", "sessions",
                    "runtime", "memories", "cron", "cache", "models_dev_cache.json",
                    ".update_check", ".skills_prompt_snapshot.json",
                ),
            )
        else:
            dst.mkdir()
        cfg = dst / "config.yaml"
        data = yaml.safe_load(cfg.read_text()) if cfg.exists() else {}
        data = data if isinstance(data, dict) else {}
        terminal = data.setdefault("terminal", {})
        if not isinstance(terminal, dict):
            terminal = data["terminal"] = {}
        # Hermes tools honor terminal.cwd rather than the launcher cwd.
        terminal["cwd"] = str(workdir.resolve())
        cfg.write_text(yaml.safe_dump(data, sort_keys=False))
        return tmp_name, dst
    except Exception:
        shutil.rmtree(dst, ignore_errors=True)
        raise


class HermesCLIAdapter(AgentAdapter):
    def __init__(self, model: str | None = None, provider: str | None = None, reasoning_effort: str | None = None, profile: str | None = None):
        super().__init__(model, provider=provider, reasoning_effort=reasoning_effort)
        self.profile = profile

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
                + ", ".join(str(a) for a in expected) + ". "
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
        cmd = ["hermes"]
        tmp_profile_dir: Path | None = None
        try:
            started_at = __import__("time").time()
            profile_name, tmp_profile_dir = _profile_with_cwd(self.profile, workdir)
            cmd += ["-p", profile_name]
            cmd += ["chat", "-q", prompt, "-Q", "--toolsets", ",".join(toolsets), "--max-turns", "20"]
            if getattr(self, "provider", None):
                cmd += ["--provider", self.provider]
            if self.model:
                cmd += ["--model", self.model]
            p = subprocess.run(cmd, cwd=workdir, text=True, capture_output=True, timeout=int(task.metadata["timeout_seconds"]))
            transcript = p.stdout + p.stderr
            telemetry = _extract_state_db_telemetry(
                tmp_profile_dir / "state.db", started_at=started_at, workdir=workdir
            ) if tmp_profile_dir is not None else StateDBTelemetry(events=[])
            return AgentRun(
                "completed" if p.returncode == 0 else "failed",
                transcript,
                telemetry.tool_calls,
                telemetry.cost_usd,
                bool(p.returncode == 0 and re.search(r"\b(done|completed|finished)\b", transcript, re.I)),
                telemetry.token_usage,
                "profile-state-db" if telemetry.trusted else None,
                tool_events=telemetry.events,
                behavior_evidence_trusted=telemetry.trusted,
            )
        finally:
            if tmp_profile_dir is not None:
                shutil.rmtree(tmp_profile_dir, ignore_errors=True)
