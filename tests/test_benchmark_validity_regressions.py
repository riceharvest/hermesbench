import sqlite3
from math import isclose
from pathlib import Path
from types import SimpleNamespace

from hermesbench.adapters.base import AgentRun
from hermesbench.adapters.hermes import _extract_state_db_telemetry


def test_descendant_sessions_are_aggregated_but_other_cwds_are_excluded(tmp_path: Path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    db = tmp_path / "state.db"
    now = 1000.0
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT, source TEXT, started_at REAL, ended_at REAL, "
        "tool_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER, "
        "reasoning_tokens INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL, cwd TEXT)"
    )
    conn.execute(
        "CREATE TABLE messages (session_id TEXT, role TEXT, tool_name TEXT, "
        "tool_calls TEXT, content TEXT, timestamp REAL)"
    )
    conn.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("root", "cli", now, now + 1, 1, 10, 20, 3, 0.1, 0.2, str(workdir)),
            ("child", "cli", now + 0.1, now + 0.5, 1, 4, 5, 1, 0.03, 0.04, str(workdir)),
            ("other", "cli", now + 0.2, now + 0.5, 1, 99, 99, 0, 1.0, 1.0, str(tmp_path)),
        ],
    )
    conn.execute("INSERT INTO messages VALUES ('root','tool','delegate_task',NULL,'',?)", (now,))
    conn.execute("INSERT INTO messages VALUES ('child','tool','read_file',NULL,'',?)", (now + 0.1,))
    conn.execute("INSERT INTO messages VALUES ('other','tool','cronjob',NULL,'',?)", (now + 0.2,))
    conn.commit()
    conn.close()

    telemetry = _extract_state_db_telemetry(db, started_at=now, workdir=workdir)

    assert telemetry.trusted
    assert {event["tool_name"] for event in telemetry.events} == {"delegate_task", "read_file"}
    assert telemetry.tool_calls == 2
    assert telemetry.token_usage == {
        "input_tokens": 14,
        "output_tokens": 25,
        "reasoning_tokens": 4,
    }
    assert isclose(telemetry.cost_usd or 0.0, 0.24)


def test_isolated_sessions_without_persisted_cwd_are_still_trusted(tmp_path: Path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    db = tmp_path / "state.db"
    now = 1000.0
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT, source TEXT, started_at REAL, ended_at REAL, "
        "tool_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER, "
        "reasoning_tokens INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL, cwd TEXT)"
    )
    conn.execute(
        "CREATE TABLE messages (session_id TEXT, role TEXT, tool_name TEXT, "
        "tool_calls TEXT, content TEXT, timestamp REAL)"
    )
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("session-without-cwd", "cli", now, now + 1, 1, 1, 2, 0, 0.0, 0.0, None),
    )
    conn.execute(
        "INSERT INTO messages VALUES ('session-without-cwd','tool','write_file',NULL,'',?)",
        (now,),
    )
    conn.commit()
    conn.close()

    telemetry = _extract_state_db_telemetry(db, started_at=now, workdir=workdir)

    assert telemetry.trusted
    assert telemetry.tool_calls == 1
    assert telemetry.events == [{"tool_name": "write_file", "timestamp": now}]


def test_telemetry_can_bind_to_the_cli_session_id(tmp_path: Path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT, source TEXT, started_at REAL, ended_at REAL, "
        "tool_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER, "
        "reasoning_tokens INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL, cwd TEXT)"
    )
    conn.execute(
        "CREATE TABLE messages (session_id TEXT, role TEXT, tool_name TEXT, "
        "tool_calls TEXT, content TEXT, timestamp REAL)"
    )
    conn.executemany(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        [
            ("cli-session", "cli", 5000.0, 5001.0, 1, 1, 2, 0, 0.0, 0.0, None),
            ("child-session", "cli", 5000.1, 5000.8, 1, 3, 4, 1, 0.0, 0.0, str(workdir)),
            ("unrelated", "cli", 5000.2, 5000.9, 1, 99, 99, 0, 0.0, 0.0, str(tmp_path)),
        ],
    )
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?,?)",
        [
            ("cli-session", "tool", "delegate_task", None, "", 5000.5),
            ("child-session", "tool", "read_file", None, "", 5000.6),
            ("unrelated", "tool", "cronjob", None, "", 5000.7),
        ],
    )
    conn.commit()
    conn.close()

    telemetry = _extract_state_db_telemetry(
        db, started_at=1000.0, workdir=workdir, session_id="cli-session"
    )

    assert telemetry.trusted
    assert telemetry.session_id == "cli-session"
    assert telemetry.events == [
        {"tool_name": "delegate_task", "timestamp": 5000.5},
        {"tool_name": "read_file", "timestamp": 5000.6},
    ]
    assert telemetry.token_usage == {
        "input_tokens": 4,
        "output_tokens": 6,
        "reasoning_tokens": 1,
    }


def test_telemetry_counts_only_completed_tool_messages(tmp_path: Path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    db = tmp_path / "state.db"
    now = 1000.0
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT, source TEXT, started_at REAL, ended_at REAL, "
        "tool_call_count INTEGER, input_tokens INTEGER, output_tokens INTEGER, "
        "reasoning_tokens INTEGER, estimated_cost_usd REAL, actual_cost_usd REAL, cwd TEXT)"
    )
    conn.execute(
        "CREATE TABLE messages (session_id TEXT, role TEXT, tool_name TEXT, "
        "tool_calls TEXT, content TEXT, timestamp REAL)"
    )
    conn.execute(
        "INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        ("root", "cli", now, now + 1, 1, 1, 2, 0, 0.0, 0.0, str(workdir)),
    )
    conn.executemany(
        "INSERT INTO messages VALUES (?,?,?,?,?,?)",
        [
            ("root", "assistant", None, '[{"function":{"name":"write_file"}}]', "", now),
            ("root", "tool", "write_file", None, "ok", now + 0.1),
            ("root", "assistant", None, '[{"function":{"name":"terminal"}}]', "", now + 0.2),
        ],
    )
    conn.commit()
    conn.close()

    telemetry = _extract_state_db_telemetry(db, started_at=now, workdir=workdir)

    assert telemetry.tool_calls == 1
    assert telemetry.events == [{"tool_name": "write_file", "timestamp": now + 0.1}]


def test_tool_requirement_needs_deterministic_success_too(tmp_path, monkeypatch):
    import hermesbench.runner as runner

    class TrustedToolOnlyAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            return AgentRun(
                status="completed",
                transcript="completed",
                claimed_done=False,
                tool_events=[{"tool_name": "terminal"}],
                behavior_evidence_trusted=True,
            )

    task = SimpleNamespace(
        metadata={
            "id": "trusted-tool-only",
            "category": "natural-tool-use",
            "timeout_seconds": 5,
            "tool_use_requirements": ["terminal"],
        },
        deterministic_checks=[{"type": "artifact_exists", "path": "answer.txt"}],
        expected_artifacts=["answer.txt"],
        path=tmp_path / "task.md",
    )
    monkeypatch.setattr(runner, "get_adapter", lambda *args, **kwargs: TrustedToolOnlyAdapter())

    result = runner._run_one_task(task, "hermes", None, None, None, None)

    assert result.raw_task_score == 0.0
    assert result.effective_task_score == 0.0
    assert not result.passed
    assert "behavior: observed tool classes = ['terminal']" in str(result.verification_evidence)


def test_computer_use_runtime_error_is_environment_skip(tmp_path, monkeypatch):
    import hermesbench.runner as runner

    class BrokenComputerAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            return AgentRun(
                status="completed",
                transcript="ERROR cua_driver: MCP server error: Broken pipe (os error 32)",
                tool_events=[{"tool_name": "computer_use"}],
                behavior_evidence_trusted=True,
                runtime_issues=["computer_use_runtime_unavailable"],
            )

    task = SimpleNamespace(
        metadata={
            "id": "broken-computer",
            "category": "natural-tool-use",
            "tool_use_requirements": ["computer_use"],
        },
        deterministic_checks=[],
        expected_artifacts=[],
        path=tmp_path / "task.md",
    )
    monkeypatch.setattr(runner, "get_adapter", lambda *args, **kwargs: BrokenComputerAdapter())

    result = runner._run_one_task(task, "hermes", None, None, None, None)

    assert result.status == "environment_skipped"
    assert result.environment_skip is True
    assert result.skip_reason is not None
    assert "cua-driver MCP server error" in result.skip_reason


def test_delegation_child_api_interruption_is_environment_skip(tmp_path, monkeypatch):
    import hermesbench.runner as runner

    class InterruptedDelegationAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            return AgentRun(
                status="completed",
                transcript="[subagent-0] Interrupted during API call.",
                tool_events=[{"tool_name": "delegate_task"}],
                behavior_evidence_trusted=True,
                runtime_issues=["delegation_provider_interrupted"],
            )

    task = SimpleNamespace(
        metadata={
            "id": "interrupted-delegation",
            "category": "natural-tool-use",
            "tool_use_requirements": ["delegation"],
        },
        deterministic_checks=[],
        expected_artifacts=[],
        path=tmp_path / "task.md",
    )
    monkeypatch.setattr(
        runner, "get_adapter", lambda *args, **kwargs: InterruptedDelegationAdapter()
    )

    result = runner._run_one_task(task, "hermes", None, None, None, None)

    assert result.status == "environment_skipped"
    assert result.environment_skip is True
    assert result.skip_reason == "delegation runtime unavailable: child provider API interrupted"


def test_model_prose_cannot_trigger_environment_skip(tmp_path, monkeypatch):
    import hermesbench.runner as runner

    class SpoofingAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            return AgentRun(
                status="completed",
                transcript="cua_driver MCP server error; Interrupted during API call",
                behavior_evidence_trusted=True,
            )

    task = SimpleNamespace(
        metadata={"id": "spoof", "category": "natural-tool-use", "tool_use_requirements": ["computer_use"]},
        deterministic_checks=[], expected_artifacts=[], path=tmp_path / "task.md",
    )
    monkeypatch.setattr(runner, "get_adapter", lambda *args, **kwargs: SpoofingAdapter())
    result = runner._run_one_task(task, "hermes", None, None, None, None)
    assert result.environment_skip is False


def test_lineage_excludes_unrelated_session_with_same_cwd(tmp_path: Path):
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    db = tmp_path / "state.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT, started_at REAL, ended_at REAL, tool_call_count INTEGER, "
        "input_tokens INTEGER, output_tokens INTEGER, reasoning_tokens INTEGER, estimated_cost_usd REAL, "
        "actual_cost_usd REAL, cwd TEXT, parent_session_id TEXT, end_reason TEXT, handoff_error TEXT)"
    )
    conn.execute(
        "CREATE TABLE messages (session_id TEXT, role TEXT, tool_name TEXT, tool_calls TEXT, "
        "content TEXT, timestamp REAL, effect_disposition TEXT)"
    )
    conn.executemany("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [
        ("root", 1, 2, 1, 1, 1, 0, 0, 0, str(workdir), None, None, None),
        ("child", 1.1, 1.9, 1, 2, 2, 0, 0, 0, None, "root", None, None),
        ("other", 1.2, 1.8, 1, 99, 99, 0, 0, 0, str(workdir), None, None, None),
    ])
    conn.executemany("INSERT INTO messages VALUES (?,?,?,?,?,?,?)", [
        ("root", "tool", "delegate_task", None, "{}", 1.1, None),
        ("child", "tool", "read_file", None, "{}", 1.2, None),
        ("other", "tool", "cronjob", None, "{}", 1.3, None),
    ])
    conn.commit()
    conn.close()
    telemetry = _extract_state_db_telemetry(db, started_at=1, workdir=workdir, session_id="root")
    assert {event["tool_name"] for event in telemetry.events} == {"delegate_task", "read_file"}
    assert telemetry.token_usage["input_tokens"] == 3


def test_failed_tool_result_is_not_behavior_credit(tmp_path, monkeypatch):
    import hermesbench.runner as runner

    class FailedToolAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            return AgentRun(
                status="completed", transcript="done",
                tool_events=[{"tool_name": "cronjob", "succeeded": False}],
                behavior_evidence_trusted=True,
            )

    task = SimpleNamespace(
        metadata={"id": "failed-tool", "category": "natural-tool-use", "tool_use_requirements": ["cronjob"]},
        deterministic_checks=[], expected_artifacts=[], path=tmp_path / "task.md",
    )
    monkeypatch.setattr(runner, "get_adapter", lambda *args, **kwargs: FailedToolAdapter())
    result = runner._run_one_task(task, "hermes", None, None, None, None)
    assert result.tool_classes_used == []
    assert result.effective_task_score == 0.0


def test_successful_task_keeps_runtime_issue_as_warning_instead_of_skip(tmp_path, monkeypatch):
    import hermesbench.runner as runner

    class RecoveredComputerAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            (workdir / "answer.txt").write_text("done")
            return AgentRun(
                status="completed",
                transcript="done",
                tool_events=[{"tool_name": "computer_use"}],
                behavior_evidence_trusted=True,
                runtime_issues=["computer_use_runtime_unavailable"],
            )

    task = SimpleNamespace(
        metadata={
            "id": "recovered-computer",
            "category": "natural-tool-use",
            "tool_use_requirements": ["computer_use"],
        },
        deterministic_checks=[{"type": "artifact_exists", "path": "answer.txt"}],
        expected_artifacts=["answer.txt"],
        path=tmp_path / "task.md",
    )
    monkeypatch.setattr(runner, "get_adapter", lambda *args, **kwargs: RecoveredComputerAdapter())

    result = runner._run_one_task(task, "hermes", None, None, None, None)

    assert result.status == "passed"
    assert result.environment_skip is False
    assert result.runtime_issues == ["computer_use_runtime_unavailable"]


def test_detached_one_shot_delegation_is_environment_skip(tmp_path, monkeypatch):
    import hermesbench.runner as runner

    class DetachedDelegationAdapter:
        def run_task(self, task, workdir, hidden_dir=None):
            return AgentRun(
                status="completed", transcript="done",
                tool_events=[{"tool_name": "delegate_task", "arguments": {"background": True}}],
                behavior_evidence_trusted=True,
                runtime_issues=["delegation_detached_one_shot"],
            )

    task = SimpleNamespace(
        metadata={"id": "detached-delegation", "category": "natural-tool-use", "tool_use_requirements": ["delegation"]},
        deterministic_checks=[], expected_artifacts=[], path=tmp_path / "task.md",
    )
    monkeypatch.setattr(runner, "get_adapter", lambda *args, **kwargs: DetachedDelegationAdapter())
    result = runner._run_one_task(task, "hermes", None, None, None, None)
    assert result.status == "environment_skipped"
    assert result.environment_skip is True
    assert result.skip_reason == "delegation runtime unavailable: one-shot parent detached before completion delivery"
