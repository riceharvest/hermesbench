from __future__ import annotations
import json, re
from pathlib import Path
from typing import Any

from .deterministic import run_checks


# Mapping of canonical tool names (as seen in Hermes telemetry) to the classes
# of capability they represent for the benchmark. We include both the Python
# function names and the names emitted in logs / tool-call telemetry.
_BEHAVIOR_TOOLS = {
    "read_file": "file",
    "read_file_tool": "file",
    "write_file": "file",
    "write_file_tool": "file",
    "patch": "file",
    "patch_tool": "file",
    "search_files": "file",
    "terminal": "terminal",
    "terminal_tool": "terminal",
    "browser_navigate": "browser",
    "browser_navigate_tool": "browser",
    "browser_click": "browser",
    "browser_click_tool": "browser",
    "browser_type": "browser",
    "browser_type_tool": "browser",
    "browser_snapshot": "browser",
    "browser_snapshot_tool": "browser",
    "web_search": "web",
    "web_search_tool": "web",
    "web_extract": "web",
    "web_extract_tool": "web",
    "mcp__fetch__fetch": "web",
    "execute_code": "code_execution",
    "execute_code_tool": "code_execution",
    "vision_analyze": "vision",
    "vision_analyze_tool": "vision",
    "image_gen": "image_gen",
    "image_gen_tool": "image_gen",
    "memory": "memory",
    "memory_tool": "memory",
    "todo": "todo",
    "todo_tool": "todo",
    "delegate_task": "delegation",
    "delegate_task_tool": "delegation",
    "clarify": "clarify",
    "clarify_tool": "clarify",
    "cronjob": "cronjob",
    "cronjob_tool": "cronjob",
    "computer_use": "computer_use",
    "computer_use_tool": "computer_use",
    "skill_view": "skills",
    "skill_view_tool": "skills",
    "skills_list": "skills",
    "skills_list_tool": "skills",
    "session_search": "session_search",
    "session_search_tool": "session_search",
    "send_message": "messaging",
    "send_message_tool": "messaging",
}


def _extract_tool_events(transcript: str) -> list[dict[str, Any]]:
    """Parse tool call events from Hermes telemetry as best we can.

    We first try JSON lines, then fallback to regex for human-readable log lines.
    """
    events: list[dict[str, Any]] = []
    for line in transcript.splitlines():
        s = line.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                obj = json.loads(s)
                if isinstance(obj, dict) and ("tool" in obj or "tool_name" in obj or "name" in obj):
                    events.append(obj)
            except json.JSONDecodeError:
                pass
    # Log lines: "agent.tool_executor: tool read_file completed (...args...)"
    for m in re.finditer(r"agent\.tool_executor: tool\s+([\w.]+)\s+completed\s*\((.*?)\)", transcript):
        events.append({"tool_name": m.group(1), "args_summary": m.group(2).strip()})
    # Telemetry line: "tool_call_count: 12" -> not an event, but confirms count
    return events


def _classify_tool(name: str | None) -> str | None:
    if not name:
        return None
    n = name.lower()
    if n in _BEHAVIOR_TOOLS:
        return _BEHAVIOR_TOOLS[n]
    # Handle namespaced variants like mcp__fetch__fetch or mcp__context7__query_docs
    if n.startswith("mcp__"):
        if "fetch" in n or "web" in n or "search" in n:
            return "web"
        return None
    # Hermes sometimes logs tools as their Python function names.
    for key, cls in _BEHAVIOR_TOOLS.items():
        if key in n or n.endswith(key) or n.startswith(key):
            return cls
    return None


def score_tool_use(workdir: Path, transcript: str, required_tool_classes: list[str]) -> tuple[float, dict[str, Any]]:
    """Score based on whether the model actually invoked the required tool classes.

    The score is 1.0 if every required tool class was observed at least once in the
    transcript, and 0.0 otherwise. We also report whether the answer was produced
    without using any tools (pure hallucination) and how many distinct tool classes
    were observed.
    """
    events = _extract_tool_events(transcript)
    observed_classes: set[str] = set()
    for ev in events:
        tool_name = ev.get("tool_name") or ev.get("tool") or ev.get("name")
        cls = _classify_tool(tool_name)
        if cls:
            observed_classes.add(cls)

    required = set(required_tool_classes)
    missing = required - observed_classes
    score = 1.0 if required and not missing else 0.0
    if not required:
        score = 0.0

    return score, {
        "observed_tool_classes": sorted(observed_classes),
        "required_tool_classes": sorted(required),
        "missing_tool_classes": sorted(missing),
        "tool_event_count": len(events),
        "used_any_tool": bool(observed_classes),
    }


def grade_behavior(task, workdir: Path, transcript: str) -> tuple[float, list[str]]:
    """Grade natural tool-use behavior for a task.

    Returns (score, evidence). The score is determined by the `tool_use_requirements`
    declared in the task metadata (list of tool classes that must be used).
    """
    required = task.metadata.get("tool_use_requirements", [])
    if not required:
        # Fallback: for backward-compatible deterministic tasks, behavior is pass-through.
        return 1.0, ["behavior: no tool-use requirements declared, skipping behavior grading"]
    score, details = score_tool_use(workdir, transcript, required)
    evidence = [
        f"behavior: required tool classes = {details['required_tool_classes']}",
        f"behavior: observed tool classes = {details['observed_tool_classes']}",
        f"behavior: missing tool classes = {details['missing_tool_classes']}",
        f"behavior: tool events seen = {details['tool_event_count']}",
        f"behavior: used any tool = {details['used_any_tool']}",
    ]
    return score, evidence
