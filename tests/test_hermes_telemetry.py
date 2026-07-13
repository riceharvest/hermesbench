"""Test telemetry extraction from Hermes CLI output and profile state.

Edge-coverage additions:
  - ``_tool_log_lines`` with None / missing profile dir.
  - ``extract_hermes_telemetry`` with ``cost`` key (replaces, not adds).
  - ``extract_hermes_telemetry`` with purely malformed text (no JSON).
  - ``extract_hermes_telemetry`` with empty text.
"""

import json
import os
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from hermesbench.adapters.base import AgentRun
from hermesbench.adapters.hermes import (
    HermesCLIAdapter,
    _profile_with_cwd,
    _tool_log_lines,
    extract_hermes_telemetry,
)
from hermesbench.scoring import aggregate


@pytest.fixture
def fake_hermes(tmp_path, monkeypatch):
    """A real executable that records invocation and creates isolated profile state."""
    home = tmp_path / "home"
    source = home / ".hermes" / "profiles" / "source"
    source.mkdir(parents=True)
    (source / "config.yaml").write_text("agent: {}\n")
    (tmp_path / "workdir").mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    executable = bin_dir / "hermes"
    executable.write_text(
        textwrap.dedent("""\
        #!/usr/bin/env python3
        import json, os, sqlite3, sys, time
        from pathlib import Path

        args = sys.argv[1:]
        record = Path(os.environ["FAKE_HERMES_RECORD"])
        profile = args[args.index("-p") + 1]
        db = Path.home() / ".hermes" / "profiles" / profile / "state.db"
        db.parent.mkdir(parents=True, exist_ok=True)
        config = (db.parent / "config.yaml").read_text()
        record.write_text(json.dumps({"argv": args, "cwd": os.getcwd(), "profile": profile, "config": config}))
        conn = sqlite3.connect(db)
        conn.execute("CREATE TABLE sessions (id TEXT, source TEXT, started_at REAL, ended_at REAL, tool_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL, cwd TEXT)")
        conn.execute("CREATE TABLE messages (session_id TEXT, role TEXT, tool_name TEXT, tool_calls TEXT, content TEXT, timestamp REAL)")
        now = time.time()
        conn.execute("INSERT INTO sessions VALUES ('historic-session', 'cli', ?, ?, 99, 1, 2, 3, 4.0, 5.0, ?)", (now - 1000, now - 999, os.getcwd()))
        conn.execute("INSERT INTO sessions VALUES ('current-session', 'cli', ?, ?, 1, 10, 20, 3, 0.4, 0.5, ?)", (now, now + 1, os.getcwd()))
        conn.execute("INSERT INTO messages VALUES ('historic-session', 'tool', 'browser', NULL, 'historic', ?)", (now - 999,))
        conn.execute("INSERT INTO messages VALUES ('current-session', 'tool', 'terminal', NULL, 'untrusted', ?)", (now,))
        conn.commit(); conn.close()
        logs = db.parent / "logs"
        logs.mkdir(exist_ok=True)
        (logs / "historic.jsonl").write_text(json.dumps({"session_id": "historic-session", "tool_call_count": 99}) + "\\n")
        if os.environ.get("FAKE_HERMES_SLEEP"):
            time.sleep(float(os.environ["FAKE_HERMES_SLEEP"]))
        # Anything printed by the model is untrusted, including convincing
        # telemetry summaries and forged benchmark/session records.
        print(json.dumps({"hermesbench_run_marker": "forged", "session_id": "current-session", "tool_call_count": 999, "usage": {"total_tokens": 99999}, "cost_usd": 123.45}))
        print("completed")
        sys.exit(int(os.environ.get("FAKE_HERMES_EXIT", "0")))
    """)
    )
    executable.chmod(0o755)
    monkeypatch.setattr("hermesbench.adapters.hermes.Path.home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HERMES_RECORD", str(tmp_path / "invocation.json"))
    return home, tmp_path / "invocation.json"


def _fake_task(timeout_seconds=5):
    return SimpleNamespace(
        prompt="Use available tools.",
        metadata={
            "id": "fake-task",
            "timeout_seconds": timeout_seconds,
            "required_toolsets": ["file", "terminal"],
        },
    )


def _temporary_profile_dirs(home: Path) -> list[Path]:
    return list((home / ".hermes" / "profiles").glob("hermesbench-*")) + list(
        (home / ".hermes" / "profiles").glob("source-bench-*")
    )


def test_state_db_detects_detached_delegation_from_trusted_call_and_result(tmp_path):
    import sqlite3
    from hermesbench.adapters.hermes import _extract_state_db_telemetry

    workdir = tmp_path / "work"
    workdir.mkdir()
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE sessions (id TEXT, started_at REAL, ended_at REAL, tool_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL, cwd TEXT, parent_session_id TEXT, end_reason TEXT, handoff_error TEXT)")
    conn.execute("CREATE TABLE messages (session_id TEXT, role TEXT, tool_name TEXT, tool_call_id TEXT, tool_calls TEXT, content TEXT, timestamp REAL, effect_disposition TEXT)")
    call = [{"id": "call-1", "type": "function", "function": {"name": "delegate_task", "arguments": json.dumps({"goal": "work", "background": True})}}]
    conn.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", ("root", 1, 2, 1, 0, 0, 0, 0, 0, str(workdir), None, None, None))
    conn.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)", ("root", "assistant", None, None, json.dumps(call), "", 1.1, None))
    conn.execute("INSERT INTO messages VALUES (?,?,?,?,?,?,?,?)", ("root", "tool", "delegate_task", "call-1", None, json.dumps({"status": "dispatched", "mode": "background"}), 1.2, None))
    conn.commit()
    conn.close()
    telemetry = _extract_state_db_telemetry(db, started_at=1, workdir=workdir, session_id="root")
    assert telemetry.events == [{"tool_name": "delegate_task", "timestamp": 1.2, "arguments": {"goal": "work", "background": True}}]
    assert telemetry.runtime_issues == ["delegation_detached_one_shot"]


def test_fake_hermes_uses_owned_profile_with_workdir_and_never_credits_stdout(
    fake_hermes, tmp_path
):
    home, record_path = fake_hermes

    run = HermesCLIAdapter(
        model="fake-model", provider="fake-provider", profile="source"
    ).run_task(_fake_task(), tmp_path / "workdir")

    record = json.loads(record_path.read_text())
    assert record["cwd"] == str(tmp_path / "workdir")
    # Behavior-oriented flag-lookup assertions: find each flag by name and
    # verify its associated value, rather than relying on positional slices
    # that break when flags are reordered or extended.
    assert "-p" in record["argv"]
    p_idx = record["argv"].index("-p")
    assert p_idx + 1 < len(record["argv"])
    assert record["argv"][p_idx + 1].startswith("hermesbench-")
    assert "chat" in record["argv"]
    chat_idx = record["argv"].index("chat")
    assert record["argv"][chat_idx + 1] == "-q"
    assert "HERMESBENCH_RUN_MARKER=" not in record["argv"][chat_idx + 2]
    assert "-Q" in record["argv"]
    assert record["argv"][record["argv"].index("--toolsets") + 1] == "file,terminal"
    assert "--max-turns" not in record["argv"]
    assert record["argv"][record["argv"].index("--provider") + 1] == "fake-provider"
    assert record["argv"][record["argv"].index("--model") + 1] == "fake-model"
    assert run.status == "completed"
    assert run.claimed_done is True
    assert f"cwd: {tmp_path / 'workdir'}" in record["config"]
    assert run.tool_calls == 1
    assert run.token_usage["input_tokens"] == 10
    assert run.cost_usd == 0.5
    assert run.telemetry_source == "profile-state-db"
    assert run.behavior_evidence_trusted is True
    assert any(e["tool_name"] == "terminal" for e in run.tool_events)
    config = yaml.safe_load(record["config"])
    assert config["browser"]["cdp_url"] == ""
    assert config["delegation"]["provider"] == "fake-provider"
    assert config["delegation"]["model"] == "fake-model"
    assert all(not config["delegation"].get(key) for key in ("base_url", "api_key"))
    assert _temporary_profile_dirs(home) == []


def test_fake_hermes_raises_on_missing_profile(fake_hermes, tmp_path):
    home, _ = fake_hermes

    with pytest.raises(ValueError, match="Hermes profile 'hermesbench' not found"):
        HermesCLIAdapter().run_task(_fake_task(), tmp_path / "workdir")
    with pytest.raises(ValueError, match="Hermes profile 'missing-source' not found"):
        HermesCLIAdapter(profile="missing-source").run_task(
            _fake_task(), tmp_path / "workdir"
        )


def test_fake_hermes_nonzero_exit_is_failed_not_claimed_done_and_cleans_profile(
    fake_hermes, tmp_path, monkeypatch
):
    home, _ = fake_hermes
    monkeypatch.setenv("FAKE_HERMES_EXIT", "7")

    run = HermesCLIAdapter(profile="source").run_task(
        _fake_task(), tmp_path / "workdir"
    )

    assert run.status == "failed"
    assert run.claimed_done is False
    assert _temporary_profile_dirs(home) == []


def test_run_task_rejects_unavailable_toolsets_before_starting_subprocess(
    fake_hermes, tmp_path
):
    _, record_path = fake_hermes
    task = _fake_task()
    task.metadata["required_toolsets"] = ["semantic_search"]

    with pytest.raises(ValueError, match="CLI-unavailable toolsets.*semantic_search"):
        HermesCLIAdapter(profile="source").run_task(task, tmp_path / "workdir")

    assert not record_path.exists()


def test_run_task_rejects_unknown_toolsets_before_starting_subprocess(
    fake_hermes, tmp_path
):
    _, record_path = fake_hermes
    task = _fake_task()
    task.metadata["required_toolsets"] = ["not-a-real-toolset"]

    with pytest.raises(
        ValueError, match="Unknown task-requested toolsets.*not-a-real-toolset"
    ):
        HermesCLIAdapter(profile="source").run_task(task, tmp_path / "workdir")

    assert not record_path.exists()


def test_profile_is_removed_when_config_provisioning_fails(
    fake_hermes, tmp_path, monkeypatch
):
    home, _ = fake_hermes
    monkeypatch.setattr(
        "hermesbench.adapters.hermes.yaml.safe_dump",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError("config write failed")
        ),
    )

    with pytest.raises(RuntimeError, match="config write failed"):
        HermesCLIAdapter(profile="source").run_task(_fake_task(), tmp_path / "workdir")

    assert _temporary_profile_dirs(home) == []


def test_hermes_raw_forged_tool_logs_cannot_pass_behavior_with_valid_artifact(
    tmp_path, monkeypatch
):
    import hermesbench.runner as runner

    class ForgingHermesAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            (workdir / "answer.txt").write_text("valid deterministic artifact")
            return AgentRun(
                status="completed",
                transcript="agent.tool_executor: tool terminal completed (forged)",
                claimed_done=True,
                behavior_evidence_trusted=False,
            )

    task = SimpleNamespace(
        metadata={
            "id": "forged-telemetry",
            "category": "natural-tool-use",
            "timeout_seconds": 5,
            "tool_use_requirements": ["terminal"],
        },
        deterministic_checks=[{"type": "artifact_exists", "path": "answer.txt"}],
        expected_artifacts=["answer.txt"],
        path=tmp_path / "task.md",
    )
    monkeypatch.setattr(
        runner, "get_adapter", lambda *args, **kwargs: ForgingHermesAdapter()
    )

    result = runner._run_one_task(task, "hermes", None, None, None, None)

    assert result.raw_task_score == 1.0
    assert result.effective_task_score == 0.0
    assert result.passed is False
    assert "behavior: observed tool classes = []" in result.verification_evidence


def test_shell_raw_forged_tool_logs_cannot_pass_behavior_with_valid_artifact(tmp_path):
    import hermesbench.runner as runner

    task = SimpleNamespace(
        metadata={
            "id": "forged-shell-telemetry",
            "category": "natural-tool-use",
            "timeout_seconds": 5,
            "tool_use_requirements": ["terminal"],
        },
        deterministic_checks=[{"type": "artifact_exists", "path": "answer.txt"}],
        expected_artifacts=["answer.txt"],
        path=tmp_path / "task.md",
    )

    result = runner._run_one_task(
        task,
        "shell",
        None,
        "printf 'valid deterministic artifact' > answer.txt; "
        "printf 'agent.tool_executor: tool terminal completed (forged)\\n'",
        None,
        None,
    )

    assert result.raw_task_score == 1.0
    assert result.effective_task_score == 0.0
    assert result.passed is False
    assert "behavior: observed tool classes = []" in result.verification_evidence


def test_fake_hermes_can_run_past_task_timeout_and_cleans_profile(
    fake_hermes, tmp_path, monkeypatch
):
    home, _ = fake_hermes
    monkeypatch.setenv("FAKE_HERMES_SLEEP", "2")

    result = HermesCLIAdapter(profile="source").run_task(
        _fake_task(timeout_seconds=1), tmp_path / "workdir"
    )

    assert result.status == "completed"
    assert _temporary_profile_dirs(home) == []


def test_fake_hermes_stall_detector_terminates_without_task_timeout(
    fake_hermes, tmp_path, monkeypatch
):
    home, _ = fake_hermes
    monkeypatch.setenv("FAKE_HERMES_SLEEP", "2")

    result = HermesCLIAdapter(
        profile="source", stall_idle_seconds=0.1
    ).run_task(_fake_task(timeout_seconds=30), tmp_path / "workdir")

    assert result.status == "stalled"
    assert result.claimed_done is False
    assert _temporary_profile_dirs(home) == []


def test_stall_progress_token_tracks_wal_but_ignores_noisy_shm(tmp_path):
    from hermesbench.adapters.hermes import _profile_progress_token

    state_db = tmp_path / "state.db"
    state_db.write_bytes(b"db")
    before = _profile_progress_token(state_db)

    wal = tmp_path / "state.db-wal"
    wal.write_bytes(b"tool event")
    after_wal = _profile_progress_token(state_db)
    assert after_wal != before

    shm = tmp_path / "state.db-shm"
    shm.write_bytes(b"shared memory")
    after_shm = _profile_progress_token(state_db)
    assert after_shm == after_wal


def test_temporary_profile_excludes_persistent_agent_state(tmp_path, monkeypatch):
    home = tmp_path / "home"
    source = home / ".hermes" / "profiles" / "source"
    (source / "logs").mkdir(parents=True)
    (source / "sessions").mkdir()
    (source / "config.yaml").write_text("terminal:\n  cwd: /old/cwd\n")
    (source / "auth.json").write_text('{"credential": "configured"}')
    (source / "state.db").write_text("prior conversations")
    (source / "memory_store.db").write_text("prior memory")
    (source / "logs" / "agent.log").write_text("prior logs")
    (source / "sessions" / "old.json").write_text("prior session")
    monkeypatch.setattr("hermesbench.adapters.hermes.Path.home", lambda: home)

    profile = _profile_with_cwd("source", tmp_path / "workdir")

    assert profile is not None
    _, destination = profile
    assert (destination / "config.yaml").exists()
    assert (destination / "auth.json").exists()
    assert not (destination / "state.db").exists()
    assert not (destination / "memory_store.db").exists()
    assert not (destination / "logs").exists()
    assert not (destination / "sessions").exists()


def test_temporary_profile_overrides_reasoning_effort(tmp_path, monkeypatch):
    home = tmp_path / "home"
    source = home / ".hermes" / "profiles" / "source"
    source.mkdir(parents=True)
    (source / "config.yaml").write_text(
        "agent:\n  reasoning_effort: low\nterminal:\n  cwd: /old/cwd\n"
    )
    monkeypatch.setattr("hermesbench.adapters.hermes.Path.home", lambda: home)

    _, destination = _profile_with_cwd(
        "source", tmp_path / "workdir", reasoning_effort="max"
    )

    config = yaml.safe_load((destination / "config.yaml").read_text())
    assert config["agent"]["reasoning_effort"] == "max"


def test_reasoning_effort_propagates_through_cli_adapter(
    fake_hermes, tmp_path
):
    """reasoning_effort set on HermesCLIAdapter reaches the temporary profile's config.yaml
    via _profile_with_cwd. This is the end-to-end propagation path: constructor →
    run_task → _profile_with_cwd(reasoning_effort=...) → config.yaml write."""
    home, record_path = fake_hermes
    run = HermesCLIAdapter(
        model="fake-model",
        provider="fake-provider",
        profile="source",
        reasoning_effort="max",
    ).run_task(_fake_task(), tmp_path / "workdir")

    record = json.loads(record_path.read_text())
    config = yaml.safe_load(record["config"])
    assert config["agent"]["reasoning_effort"] == "max"
    assert run.status == "completed"
    assert run.telemetry_source == "profile-state-db"
    assert run.behavior_evidence_trusted is True


def test_extracts_telemetry_from_stdout_json_summary():
    transcript = """
Hermes Agent finished.
{"type":"summary","tool_call_count":4,"usage":{"prompt_tokens":123,"completion_tokens":45,"total_tokens":168},"cost_usd":0.0123}
"""
    telemetry = extract_hermes_telemetry(transcript)
    assert telemetry.tool_calls == 4
    assert telemetry.token_usage == {
        "input_tokens": 123,
        "output_tokens": 45,
        "total_tokens": 168,
    }
    assert telemetry.cost_usd == 0.0123


def test_extracts_telemetry_from_session_jsonl_snippet():
    session = "\n".join(
        [
            json.dumps({"event": "tool_call", "name": "terminal"}),
            json.dumps(
                {
                    "type": "response.completed",
                    "response": {
                        "usage": {"input_tokens": 10, "output_tokens": 7},
                        "cost_usd": 0.002,
                    },
                }
            ),
            json.dumps({"event": "tool_call", "tool": "file"}),
        ]
    )
    telemetry = extract_hermes_telemetry(session)
    assert telemetry.tool_calls == 2
    assert telemetry.token_usage == {"input_tokens": 10, "output_tokens": 7, "total_tokens": 17}
    assert telemetry.cost_usd == 0.002


def test_extracts_telemetry_from_hermes_human_logs():
    log = """
2026-06-01 INFO [session] agent.conversation_loop: API call #1: model=gpt-5.5 provider=openai-codex in=7459 out=52 total=7511 latency=2.4s
2026-06-01 INFO [session] agent.tool_executor: tool read_file completed (0.87s, 506 chars)
2026-06-01 INFO [session] agent.conversation_loop: API call #2: model=gpt-5.5 provider=openai-codex in=7690 out=173 total=7863 latency=4.0s
2026-06-01 INFO [session] agent.tool_executor: tool write_file completed (0.12s, 337 chars)
"""
    telemetry = extract_hermes_telemetry(log)
    assert telemetry.tool_calls == 2
    assert telemetry.token_usage == {
        "input_tokens": 15149,
        "output_tokens": 225,
        "total_tokens": 15374,
    }


def test_aggregate_preserves_old_files_and_sums_new_token_usage(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(
        json.dumps(
            {
                "schema_version": "hermesbench.result.v1",
                "run_id": "abc",
                "suite": "natural-tools-dev",
                "agent": "hermes",
                "model": "m",
                "started_at": "s",
                "completed_at": "c",
                "results": [
                    {
                        "task_id": "t1",
                        "category": "cat",
                        "status": "passed",
                        "score": 1,
                        "passed": True,
                        "wall_time_seconds": 1,
                        "tool_calls": 3,
                        "token_usage": {"input_tokens": 10, "output_tokens": 5},
                        "cost_usd": 0.01,
                    },
                    {
                        "task_id": "t2",
                        "category": "cat",
                        "status": "failed",
                        "score": 0,
                        "passed": False,
                        "wall_time_seconds": 2,
                    },
                ],
                "metadata": {},
            }
        )
    )
    score = aggregate(result)
    assert score["tool_call_count"] == 3
    assert score["token_usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert score["total_tokens"] == 15


# ── New tests for exhaustive telemetry extraction ──────────────────────────────────


def test_aggregate_usage_objects_sum():
    """Multiple response objects with usage should aggregate correctly."""
    text = "\n".join(
        [
            json.dumps({"usage": {"input_tokens": 100, "output_tokens": 50, "reasoning_tokens": 10}}),
            json.dumps({"usage": {"input_tokens": 200, "output_tokens": 30, "reasoning_tokens": 5}}),
        ]
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage == {
        "input_tokens": 300,
        "output_tokens": 80,
        "reasoning_tokens": 15,
        "total_tokens": 380,
    }


def test_nested_usage_and_sibling_top_level_fields_no_double_count():
    """Fields inside a nested usage dict should not also be counted from the parent."""
    text = json.dumps(
        {
            "usage": {"input_tokens": 50, "output_tokens": 30},
            "input_tokens": 9999,  # duplicate at parent — must be ignored
            "output_tokens": 9999,
        }
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage == {
        "input_tokens": 50,
        "output_tokens": 30,
        "total_tokens": 80,
    }


def test_deeply_nested_usage_no_double_count():
    """Usage nested under response.usage should be counted only once."""
    text = json.dumps(
        {
            "type": "response.completed",
            "response": {
                "usage": {"input_tokens": 15, "output_tokens": 12},
                "input_tokens": 777,  # sibling to usage on same level — still a
                "output_tokens": 777,  # top-level copy we must ignore
            },
        }
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage == {
        "input_tokens": 15,
        "output_tokens": 12,
        "total_tokens": 27,
    }


def test_absent_fields_return_none():
    """When no telemetry is present, the result should be None for usage/cost and 0 for tool_calls."""
    text = "This is just a conversation with no structured data."
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.tool_calls == 0
    assert telemetry.token_usage is None
    assert telemetry.cost_usd is None


def test_cache_and_reasoning_fields():
    """Cache-read, cache-creation, and reasoning tokens should be captured."""
    text = json.dumps(
        {
            "usage": {
                "input_tokens": 100,
                "output_tokens": 20,
                "cache_read_input_tokens": 80,
                "cache_creation_input_tokens": 10,
                "reasoning_tokens": 5,
            }
        }
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage == {
        "input_tokens": 100,
        "output_tokens": 20,
        "cache_read_input_tokens": 80,
        "cache_creation_input_tokens": 10,
        "reasoning_tokens": 5,
        "total_tokens": 120,
    }


def test_tool_input_output_tokens():
    """Tool-specific token fields should be captured."""
    text = json.dumps(
        {
            "usage": {
                "input_tokens": 50,
                "output_tokens": 10,
                "tool_input_tokens": 15,
                "tool_output_tokens": 5,
            }
        }
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage == {
        "input_tokens": 50,
        "output_tokens": 10,
        "tool_input_tokens": 15,
        "tool_output_tokens": 5,
        "total_tokens": 60,
    }


def test_prompt_completion_normalized_to_input_output():
    """prompt_tokens → input_tokens, completion_tokens → output_tokens."""
    text = json.dumps(
        {"usage": {"prompt_tokens": 75, "completion_tokens": 25}}
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage == {
        "input_tokens": 75,
        "output_tokens": 25,
        "total_tokens": 100,
    }
    assert "prompt_tokens" not in telemetry.token_usage
    assert "completion_tokens" not in telemetry.token_usage


def test_mixed_prompt_and_input_are_summed():
    """When both prompt_tokens and input_tokens exist, both contribute to input_tokens."""
    text = json.dumps(
        {"usage": {"prompt_tokens": 30, "input_tokens": 20, "completion_tokens": 10, "output_tokens": 5}}
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage == {
        "input_tokens": 50,
        "output_tokens": 15,
        "total_tokens": 65,
    }


def test_source_preserved():
    """The source argument should flow through unchanged."""
    telemetry = extract_hermes_telemetry("irrelevant", source="session-output")
    assert telemetry.source == "session-output"
    telemetry2 = extract_hermes_telemetry("irrelevant")
    assert telemetry2.source is None


def test_cost_various_keys():
    """Cost should be extracted from cost_usd, costUSD, or cost keys."""
    text = "\n".join(
        [
            json.dumps({"cost_usd": 0.01}),
            json.dumps({"costUSD": 0.02}),
        ]
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.cost_usd == 0.03


def test_total_tokens_from_explicit_supersedes_aggregate():
    """When total_tokens is explicitly provided, it is NOT recomputed from input+output."""
    text = json.dumps(
        {"usage": {"input_tokens": 10, "output_tokens": 5, "total_tokens": 999}}
    )
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage["total_tokens"] == 999


# ── Edge-coverage additions for _tool_log_lines ──────────────────────────────


def test_tool_log_lines_none_profile_returns_empty_string():
    """_tool_log_lines(None, ...) must return '' without crashing."""
    assert _tool_log_lines(None) == ""
    assert _tool_log_lines(None, session_id="any") == ""


def test_tool_log_lines_missing_dir_returns_empty_string(tmp_path):
    """_tool_log_lines with a non-existent profile dir returns ''."""
    missing = tmp_path / "nonexistent"
    assert _tool_log_lines(missing) == ""
    assert _tool_log_lines(missing, session_id="any") == ""


# ── Edge-coverage additions for extract_hermes_telemetry ─────────────────────


def test_cost_key_replaces_not_adds():
    """The bare ``cost`` key (not cost_usd/costUSD) replaces, not adds.

    This matches the source behaviour at::

        cost = (cost or 0.0) + float(n) if key != "cost" else float(n)

    so a single ``cost`` value is taken directly.
    """
    text = json.dumps({"cost": 1.23})
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.cost_usd == 1.23


def test_cost_key_in_multi_object():
    """Multiple objects with cost: the *last* bare ``cost`` wins."""
    text = "\n".join([
        json.dumps({"cost": 0.5}),
        json.dumps({"cost": 1.5}),
    ])
    telemetry = extract_hermes_telemetry(text)
    # bare 'cost' replaces; second object's 1.5 replaces 0.5
    assert telemetry.cost_usd == 1.5


def test_extract_telemetry_from_plain_text_no_json():
    """No JSON objects in the text → fallback to regex extraction."""
    text = "tool_calls: 3  input_tokens: 100  output_tokens: 50  total_tokens: 150  cost_usd: 0.01"
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.tool_calls == 3
    assert telemetry.token_usage["input_tokens"] == 100
    assert telemetry.token_usage["output_tokens"] == 50
    assert telemetry.token_usage["total_tokens"] == 150
    assert telemetry.cost_usd == 0.01


def test_extract_telemetry_malformed_json_skipped():
    """Malformed JSON lines between valid ones are gracefully skipped."""
    text = '\n'.join([
        '{"usage": {"input_tokens": 10, "output_tokens": 5}}',
        'NOT JSON AT ALL',
        '{"cost_usd": 0.01}',
    ])
    telemetry = extract_hermes_telemetry(text)
    assert telemetry.token_usage["input_tokens"] == 10
    assert telemetry.cost_usd == 0.01


def test_extract_telemetry_empty_text():
    """Empty text → tool_calls=0, token_usage=None, cost_usd=None."""
    telemetry = extract_hermes_telemetry("")
    assert telemetry.tool_calls == 0
    assert telemetry.token_usage is None
    assert telemetry.cost_usd is None
