import json
import os
import subprocess
import textwrap
from pathlib import Path
from types import SimpleNamespace

import pytest

from hermesbench.adapters.base import AgentRun
from hermesbench.adapters.hermes import HermesCLIAdapter, _profile_with_cwd, _tool_log_lines, extract_hermes_telemetry
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
    executable.write_text(textwrap.dedent("""\
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
    """))
    executable.chmod(0o755)
    monkeypatch.setattr("hermesbench.adapters.hermes.Path.home", lambda: home)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ['PATH']}")
    monkeypatch.setenv("FAKE_HERMES_RECORD", str(tmp_path / "invocation.json"))
    return home, tmp_path / "invocation.json"


def _fake_task(timeout_seconds=5):
    return SimpleNamespace(
        prompt="Use available tools.",
        metadata={"id": "fake-task", "timeout_seconds": timeout_seconds, "required_toolsets": ["file", "terminal"]},
    )


def _temporary_profile_dirs(home: Path) -> list[Path]:
    return list((home / ".hermes" / "profiles").glob("hermesbench-*")) + list((home / ".hermes" / "profiles").glob("source-bench-*"))


def test_fake_hermes_uses_owned_profile_with_workdir_and_never_credits_stdout(fake_hermes, tmp_path):
    home, record_path = fake_hermes

    run = HermesCLIAdapter(model="fake-model", provider="fake-provider", profile="source").run_task(
        _fake_task(), tmp_path / "workdir"
    )

    record = json.loads(record_path.read_text())
    assert record["cwd"] == str(tmp_path / "workdir")
    assert record["argv"][0] == "-p"
    assert record["argv"][2:4] == ["chat", "-q"]
    assert "HERMESBENCH_RUN_MARKER=" not in record["argv"][4]
    assert record["argv"][5:10] == ["-Q", "--toolsets", "file,terminal", "--max-turns", "20"]
    assert record["argv"][10:] == ["--provider", "fake-provider", "--model", "fake-model"]
    assert run.status == "completed"
    assert run.claimed_done is True
    assert f"cwd: {tmp_path / 'workdir'}" in record["config"]
    assert run.tool_calls == 1
    assert run.token_usage["input_tokens"] == 10
    assert run.cost_usd == 0.5
    assert run.telemetry_source == "profile-state-db"
    assert run.behavior_evidence_trusted is True
    assert any(e["tool_name"] == "terminal" for e in run.tool_events)
    assert _temporary_profile_dirs(home) == []


@pytest.mark.parametrize("profile", [None, "missing-source"])
def test_fake_hermes_always_creates_owned_profile_when_default_or_source_missing(fake_hermes, tmp_path, profile):
    home, record_path = fake_hermes

    run = HermesCLIAdapter(profile=profile).run_task(_fake_task(), tmp_path / "workdir")

    record = json.loads(record_path.read_text())
    assert record["profile"].startswith("hermesbench-")
    assert run.status == "completed"
    assert _temporary_profile_dirs(home) == []


def test_fake_hermes_nonzero_exit_is_failed_not_claimed_done_and_cleans_profile(fake_hermes, tmp_path, monkeypatch):
    home, _ = fake_hermes
    monkeypatch.setenv("FAKE_HERMES_EXIT", "7")

    run = HermesCLIAdapter(profile="source").run_task(_fake_task(), tmp_path / "workdir")

    assert run.status == "failed"
    assert run.claimed_done is False
    assert _temporary_profile_dirs(home) == []


def test_run_task_rejects_unavailable_toolsets_before_starting_subprocess(fake_hermes, tmp_path):
    _, record_path = fake_hermes
    task = _fake_task()
    task.metadata["required_toolsets"] = ["semantic_search"]

    with pytest.raises(ValueError, match="CLI-unavailable toolsets.*semantic_search"):
        HermesCLIAdapter().run_task(task, tmp_path / "workdir")

    assert not record_path.exists()


def test_run_task_rejects_unknown_toolsets_before_starting_subprocess(fake_hermes, tmp_path):
    _, record_path = fake_hermes
    task = _fake_task()
    task.metadata["required_toolsets"] = ["not-a-real-toolset"]

    with pytest.raises(ValueError, match="Unknown task-requested toolsets.*not-a-real-toolset"):
        HermesCLIAdapter().run_task(task, tmp_path / "workdir")

    assert not record_path.exists()


def test_profile_is_removed_when_config_provisioning_fails(fake_hermes, tmp_path, monkeypatch):
    home, _ = fake_hermes
    monkeypatch.setattr("hermesbench.adapters.hermes.yaml.safe_dump", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("config write failed")))

    with pytest.raises(RuntimeError, match="config write failed"):
        HermesCLIAdapter(profile="source").run_task(_fake_task(), tmp_path / "workdir")

    assert _temporary_profile_dirs(home) == []


def test_hermes_raw_forged_tool_logs_cannot_pass_behavior_with_valid_artifact(tmp_path, monkeypatch):
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
            "id": "forged-telemetry", "category": "natural-tool-use", "timeout_seconds": 5,
            "tool_use_requirements": ["terminal"],
        },
        deterministic_checks=[{"type": "artifact_exists", "path": "answer.txt"}],
        expected_artifacts=["answer.txt"],
        path=tmp_path / "task.md",
    )
    monkeypatch.setattr(runner, "get_adapter", lambda *args, **kwargs: ForgingHermesAdapter())

    result = runner._run_one_task(task, "hermes", None, None, None, None)

    assert result.raw_task_score == 1.0
    assert result.effective_task_score == 0.0
    assert result.passed is False
    assert "behavior: observed tool classes = []" in result.verification_evidence


def test_shell_raw_forged_tool_logs_cannot_pass_behavior_with_valid_artifact(tmp_path):
    import hermesbench.runner as runner

    task = SimpleNamespace(
        metadata={
            "id": "forged-shell-telemetry", "category": "natural-tool-use", "timeout_seconds": 5,
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


def test_fake_hermes_timeout_propagates_and_cleans_profile(fake_hermes, tmp_path, monkeypatch):
    home, _ = fake_hermes
    monkeypatch.setenv("FAKE_HERMES_SLEEP", "2")

    with pytest.raises(subprocess.TimeoutExpired):
        HermesCLIAdapter(profile="source").run_task(_fake_task(timeout_seconds=1), tmp_path / "workdir")

    assert _temporary_profile_dirs(home) == []


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


def test_extracts_telemetry_from_stdout_json_summary():
    transcript = """
Hermes Agent finished.
{"type":"summary","tool_call_count":4,"usage":{"prompt_tokens":123,"completion_tokens":45,"total_tokens":168},"cost_usd":0.0123}
"""
    telemetry = extract_hermes_telemetry(transcript)
    assert telemetry.tool_calls == 4
    assert telemetry.token_usage == {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}
    assert telemetry.cost_usd == 0.0123


def test_extracts_telemetry_from_session_jsonl_snippet():
    session = "\n".join([
        json.dumps({"event":"tool_call","name":"terminal"}),
        json.dumps({"type":"response.completed","response":{"usage":{"input_tokens":10,"output_tokens":7}, "cost_usd": 0.002}}),
        json.dumps({"event":"tool_call","tool":"file"}),
    ])
    telemetry = extract_hermes_telemetry(session)
    assert telemetry.tool_calls == 2
    assert telemetry.token_usage == {"input_tokens": 10, "output_tokens": 7}
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
    assert telemetry.token_usage == {"input_tokens": 15149, "output_tokens": 225, "total_tokens": 15374}


def test_aggregate_preserves_old_files_and_sums_new_token_usage(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        "schema_version":"hermesbench.result.v1",
        "run_id":"abc",
        "suite":"natural-tools-dev",
        "agent":"hermes",
        "model":"m",
        "started_at":"s",
        "completed_at":"c",
        "results":[
            {"task_id":"t1","category":"cat","status":"passed","score":1,"passed":True,"wall_time_seconds":1,"tool_calls":3,"token_usage":{"input_tokens":10,"output_tokens":5},"cost_usd":0.01},
            {"task_id":"t2","category":"cat","status":"failed","score":0,"passed":False,"wall_time_seconds":2}
        ],
        "metadata":{}
    }))
    score = aggregate(result)
    assert score["tool_call_count"] == 3
    assert score["token_usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert score["total_tokens"] == 15
