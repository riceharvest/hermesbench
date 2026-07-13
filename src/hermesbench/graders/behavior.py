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
    "browser_cdp": "browser_cdp",
    "browser_cdp_tool": "browser_cdp",
    "browser_dialog": "browser_cdp",
    "browser_dialog_tool": "browser_cdp",
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
    "image_generate": "image_gen",
    "image_generate_tool": "image_gen",
    "video_analyze": "video",
    "video_analyze_tool": "video",
    "video_generate": "video_gen",
    "video_generate_tool": "video_gen",
    "xai_video_edit": "video_gen",
    "xai_video_edit_tool": "video_gen",
    "xai_video_extend": "video_gen",
    "xai_video_extend_tool": "video_gen",
    "text_to_speech": "tts",
    "text_to_speech_tool": "tts",
    "memory": "memory",
    "memory_tool": "memory",
    "fact_store": "memory",
    "fact_store_tool": "memory",
    "fact_feedback": "memory",
    "fact_feedback_tool": "memory",
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
    "semantic_search": "semantic_search",
    "semantic_search_tool": "semantic_search",
    "ha_list_entities": "homeassistant",
    "ha_list_entities_tool": "homeassistant",
    "ha_get_state": "homeassistant",
    "ha_get_state_tool": "homeassistant",
    "ha_list_services": "homeassistant",
    "ha_list_services_tool": "homeassistant",
    "ha_call_service": "homeassistant",
    "ha_call_service_tool": "homeassistant",
    "kanban_show": "kanban",
    "kanban_show_tool": "kanban",
    "kanban_list": "kanban",
    "kanban_list_tool": "kanban",
    "kanban_complete": "kanban",
    "kanban_complete_tool": "kanban",
    "kanban_block": "kanban",
    "kanban_block_tool": "kanban",
    "kanban_heartbeat": "kanban",
    "kanban_heartbeat_tool": "kanban",
    "kanban_comment": "kanban",
    "kanban_comment_tool": "kanban",
    "kanban_create": "kanban",
    "kanban_create_tool": "kanban",
    "kanban_link": "kanban",
    "kanban_link_tool": "kanban",
    "kanban_unblock": "kanban",
    "kanban_unblock_tool": "kanban",
    "project_list": "project",
    "project_list_tool": "project",
    "project_create": "project",
    "project_create_tool": "project",
    "project_switch": "project",
    "project_switch_tool": "project",
    "discord": "discord",
    "discord_tool": "discord",
    "discord_admin": "discord_admin",
    "discord_admin_tool": "discord_admin",
    "x_search": "x_search",
    "x_search_tool": "x_search",
    "yb_query_group_info": "yuanbao",
    "yb_query_group_info_tool": "yuanbao",
    "yb_query_group_members": "yuanbao",
    "yb_query_group_members_tool": "yuanbao",
    "yb_send_dm": "yuanbao",
    "yb_send_dm_tool": "yuanbao",
    "yb_search_sticker": "yuanbao",
    "yb_search_sticker_tool": "yuanbao",
    "yb_send_sticker": "yuanbao",
    "yb_send_sticker_tool": "yuanbao",
    "spotify_playback": "spotify",
    "spotify_playback_tool": "spotify",
    "spotify_devices": "spotify",
    "spotify_devices_tool": "spotify",
    "spotify_queue": "spotify",
    "spotify_queue_tool": "spotify",
    "spotify_search": "spotify",
    "spotify_search_tool": "spotify",
    "spotify_playlists": "spotify",
    "spotify_playlists_tool": "spotify",
    "spotify_albums": "spotify",
    "spotify_albums_tool": "spotify",
    "spotify_library": "spotify",
    "spotify_library_tool": "spotify",
    "feishu_doc_read": "feishu",
    "feishu_doc_read_tool": "feishu",
    "feishu_drive_add_comment": "feishu",
    "feishu_drive_add_comment_tool": "feishu",
    "feishu_drive_list_comments": "feishu",
    "feishu_drive_list_comments_tool": "feishu",
    "feishu_drive_list_comment_replies": "feishu",
    "feishu_drive_list_comment_replies_tool": "feishu",
    "feishu_drive_reply_comment": "feishu",
    "feishu_drive_reply_comment_tool": "feishu",
    "send_message": "messaging",
    "send_message_tool": "messaging",
    "speech_to_text": "stt",
    "speech_to_text_tool": "stt",
    "transcribe_audio": "stt",
    "transcribe_audio_tool": "stt",
    "obsidian_read": "obsidian",
    "obsidian_read_tool": "obsidian",
    "obsidian_search": "obsidian",
    "obsidian_search_tool": "obsidian",
    "obsidian_write": "obsidian",
    "obsidian_write_tool": "obsidian",
    "gh_pr_create": "github",
    "gh_pr_create_tool": "github",
    "gh_workflow_run": "github",
    "gh_workflow_run_tool": "github",
    "github": "github",
    "github_tool": "github",
    "docker_ps": "docker",
    "docker_ps_tool": "docker",
    "docker_run": "docker",
    "docker_run_tool": "docker",
    "docker_logs": "docker",
    "docker_logs_tool": "docker",
    "docker": "docker",
    "docker_tool": "docker",
    "notion_page_read": "notion",
    "notion_page_read_tool": "notion",
    "notion_database_query": "notion",
    "notion_database_query_tool": "notion",
    "notion": "notion",
    "notion_tool": "notion",
    "linear_issue_create": "linear",
    "linear_issue_create_tool": "linear",
    "linear_search": "linear",
    "linear_search_tool": "linear",
    "linear": "linear",
    "linear_tool": "linear",
    "maps_geocode": "maps",
    "maps_geocode_tool": "maps",
    "maps_pois": "maps",
    "maps_pois_tool": "maps",
    "maps_route": "maps",
    "maps_route_tool": "maps",
    "maps": "maps",
    "maps_tool": "maps",
    "himalaya_send": "himalaya",
    "himalaya_send_tool": "himalaya",
    "himalaya_read": "himalaya",
    "himalaya_read_tool": "himalaya",
    "himalaya_list": "himalaya",
    "himalaya_list_tool": "himalaya",
    "himalaya": "himalaya",
    "himalaya_tool": "himalaya",
    "openhue_light_set": "openhue",
    "openhue_light_set_tool": "openhue",
    "openhue_scene_activate": "openhue",
    "openhue_scene_activate_tool": "openhue",
    "openhue": "openhue",
    "openhue_tool": "openhue",
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


def grade_behavior(task, workdir: Path, transcript: str, *, trusted: bool = True) -> tuple[float, list[str]]:
    """Grade natural tool-use behavior for a task.

    Returns (score, evidence). The score is determined by the `tool_use_requirements`
    declared in the task metadata (list of tool classes that must be used).
    """
    required = task.metadata.get("tool_use_requirements", [])
    if not required:
        # Fallback: for backward-compatible deterministic tasks, behavior is pass-through.
        return 1.0, ["behavior: no tool-use requirements declared, skipping behavior grading"]
    if not trusted:
        return 0.0, [
            f"behavior: required tool classes = {sorted(set(required))}",
            "behavior: observed tool classes = []",
            f"behavior: missing tool classes = {sorted(set(required))}",
            "behavior: tool events seen = 0",
            "behavior: used any tool = False",
            "behavior: trusted tool evidence unavailable; raw transcript was not graded",
        ]
    score, details = score_tool_use(workdir, transcript, required)
    evidence = [
        f"behavior: required tool classes = {details['required_tool_classes']}",
        f"behavior: observed tool classes = {details['observed_tool_classes']}",
        f"behavior: missing tool classes = {details['missing_tool_classes']}",
        f"behavior: tool events seen = {details['tool_event_count']}",
        f"behavior: used any tool = {details['used_any_tool']}",
    ]
    return score, evidence
