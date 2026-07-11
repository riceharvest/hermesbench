"""Tests for run-ledger schema (RunLedgerMetadata) and run-level wall time."""

import json
import threading
import time
from pathlib import Path

from hermesbench.schemas import (
    RunLedgerMetadata,
    RunResult,
    TaskResult,
    MAX_RESULT_METADATA_KEYS,
    RESULT_SCHEMA_VERSION,
    validate_result_schema,
)
from hermesbench.runner import (
    _collect_git_commit,
    _collect_system_metadata,
    _collect_run_metadata,
    _safe_command,
    run_benchmark,
)


# ── RunLedgerMetadata unit tests ──────────────────────────────────────────


class TestRunLedgerMetadataToFromDict:
    def test_command_redacts_inline_credentials(self):
        safe = _safe_command(
            "hermes --api-key=sk-secret --authorization Bearer-secret --model x"
        )
        assert safe is not None
        assert "sk-secret" not in safe
        assert "Bearer-secret" not in safe
        assert "--model x" in safe

    def test_minimal_roundtrip(self):
        """A bare-minimum RunLedgerMetadata serializes and deserializes."""
        meta = RunLedgerMetadata()
        d = meta.to_metadata_dict()
        # Always includes metadata_available marker.
        assert d == {"metadata_available": {}}
        restored = RunLedgerMetadata.from_metadata_dict(d)
        assert restored.provider is None
        assert restored.metadata_available == {}

    def test_full_roundtrip(self):
        """All populated fields survive to_metadata_dict -> from_metadata_dict."""
        meta = RunLedgerMetadata(
            provider="deepseek",
            model="deepseek-chat",
            reasoning_effort="high",
            quantization=None,
            backend="native",
            profile="hermesbench",
            benchmark_version="core-cli-v0.1",
            jobs=2,
            run_wall_time_seconds=12.345,
            git_commit="abc1234",
            command="hermesbench run --suite core-cli",
            os_platform="Linux-7.1.3-x86_64",
            python_version="3.11.14",
            cpu_info="AMD EPYC; 8 cores",
            gpu_info="1x NVIDIA A100",
            metadata_available={
                "model_identity": True,
                "runtime": True,
                "provenance": True,
                "hardware": True,
                "timing": True,
            },
        )
        d = meta.to_metadata_dict()
        # metadata_available must be present.
        assert "metadata_available" in d
        assert d["metadata_available"]["model_identity"] is True
        # Serialized keys match the populated fields.
        assert d["provider"] == "deepseek"
        assert d["run_wall_time_seconds"] == 12.345
        assert d["cpu_info"] == "AMD EPYC; 8 cores"

        restored = RunLedgerMetadata.from_metadata_dict(d)
        assert restored.provider == "deepseek"
        assert restored.model == "deepseek-chat"
        assert restored.quantization is None  # explicitly set None -> omitted
        assert restored.run_wall_time_seconds == 12.345
        assert restored.metadata_available["timing"] is True

    def test_none_fields_omitted_from_dict(self):
        """Fields set to None are excluded from to_metadata_dict to save keys."""
        meta = RunLedgerMetadata(provider="openai")
        d = meta.to_metadata_dict()
        assert d["provider"] == "openai"
        assert "model" not in d
        assert "reasoning_effort" not in d
        assert "quantization" not in d

    def test_fits_within_metadata_key_limit(self):
        """A realistically populated RunLedgerMetadata stays within the 20-key limit,
        even including the 3 runner-specific dict entries."""
        meta = RunLedgerMetadata(
            provider="p",
            model="m",
            reasoning_effort="r",
            quantization="q",
            backend="b",
            profile="pr",
            benchmark_version="v",
            jobs=4,
            run_wall_time_seconds=1.0,
            git_commit="gc",
            command="cmd",
            os_platform="os",
            python_version="py",
            cpu_info="cpu",
            gpu_info="gpu",
            metadata_available={"all": True},
        )
        d = meta.to_metadata_dict()
        assert len(d) <= MAX_RESULT_METADATA_KEYS, (
            f"to_metadata_dict produced {len(d)} keys, "
            f"exceeds MAX_RESULT_METADATA_KEYS={MAX_RESULT_METADATA_KEYS}"
        )
        # Including the 3 flat runner keys (task_count,
        # public_output_redacts_hidden_checks, task_root) we must still
        # stay within 20.
        total_with_runner = len(d) + 3
        assert total_with_runner <= MAX_RESULT_METADATA_KEYS, (
            f"meta keys {len(d)} + runner keys 3 = {total_with_runner} "
            f"exceeds MAX_RESULT_METADATA_KEYS={MAX_RESULT_METADATA_KEYS}"
        )


class TestRunLedgerMetadataBackwardCompat:
    def test_existing_result_passes_validate(self):
        """A RunResult using the new metadata shape still passes validate_result_schema."""
        tr = TaskResult(
            task_id="t1",
            category="natural-tool-use",
            status="passed",
            score=1.0,
            passed=True,
            wall_time_seconds=1.0,
        )
        result = RunResult(
            schema_version=RESULT_SCHEMA_VERSION,
            run_id="test-ledger-bc",
            suite="core-cli",
            agent="hermes",
            model="deepseek-chat",
            started_at="2026-07-10T00:00:00Z",
            completed_at="2026-07-10T00:01:00Z",
            results=[tr],
            metadata={
                "task_count": 1,
                "public_output_redacts_hidden_checks": True,
                "task_root": None,
                "provider": "deepseek",
                "model": "deepseek-chat",
                "profile": "hermesbench",
                "benchmark_version": "core-cli-v0.1",
                "jobs": 1,
                "run_wall_time_seconds": 5.0,
                "os_platform": "Linux-x86_64",
                "python_version": "3.11",
                "cpu_info": "x86_64; 4 cores",
                "metadata_available": {"timing": True},
            },
        )
        # Must not raise.
        validate_result_schema(result.to_jsonable())

    def test_metadata_key_count_with_all_runner_fields(self):
        """A realistic run metadata dict stays within MAX_RESULT_METADATA_KEYS."""
        meta = _collect_run_metadata(
            provider="deepseek",
            model="deepseek-chat",
            reasoning_effort="high",
            quantization=None,
            backend="native",
            profile="hermesbench",
            benchmark_version="core-cli-v0.1",
            jobs=2,
            run_wall_time_seconds=15.0,
            command="hermesbench run ...",
        )
        d = meta.to_metadata_dict()
        # Add the 3 runner-specific fields always present in the flat dict.
        runner_specific = {"task_count", "public_output_redacts_hidden_checks", "task_root"}
        total_keys = len(d) + len(runner_specific)
        assert total_keys <= MAX_RESULT_METADATA_KEYS, (
            f"total keys {total_keys} exceeds {MAX_RESULT_METADATA_KEYS}"
        )


# ── Collector function tests ──────────────────────────────────────────────


class TestCollectGitCommit:
    def test_returns_string_or_none(self):
        """_collect_git_commit returns either a short hash or None (not crash)."""
        commit = _collect_git_commit()
        # In a real git repo it's a hash; in test env it could be None.
        if commit is not None:
            assert len(commit) >= 7
            assert all(c in "0123456789abcdef" for c in commit)


class TestCollectSystemMetadata:
    def test_returns_dict_with_expected_keys(self):
        info = _collect_system_metadata()
        assert "os_platform" in info
        assert "python_version" in info
        assert "cpu_info" in info
        # gpu_info may be None if no nvidia-smi available — that's fine.
        assert info["os_platform"] is not None
        assert info["python_version"] is not None
        assert info["cpu_info"] is not None


class TestCollectRunMetadata:
    def test_builds_ledger_with_provided_fields(self):
        meta = _collect_run_metadata(
            provider="test-provider",
            model="test-model",
            reasoning_effort="low",
            quantization="Q4_K_M",
            backend="llama.cpp",
            profile="test-profile",
            benchmark_version="test-v1",
            jobs=1,
            run_wall_time_seconds=3.14,
            command="run --test",
        )
        assert meta.provider == "test-provider"
        assert meta.model == "test-model"
        assert meta.reasoning_effort == "low"
        assert meta.quantization == "Q4_K_M"
        assert meta.backend == "llama.cpp"
        assert meta.profile == "test-profile"
        assert meta.benchmark_version == "test-v1"
        assert meta.jobs == 1
        assert meta.run_wall_time_seconds == 3.14
        assert meta.command == "run --test"

    def test_disovers_system_metadata(self):
        meta = _collect_run_metadata(
            provider=None,
            model=None,
            reasoning_effort=None,
            quantization=None,
            backend=None,
            profile="test",
            benchmark_version=None,
            jobs=None,
            run_wall_time_seconds=None,
        )
        # System info should always be populated on any real machine.
        assert meta.os_platform is not None
        assert meta.python_version is not None
        assert meta.cpu_info is not None

    def test_availability_markers(self):
        meta = _collect_run_metadata(
            provider="deepseek",
            model=None,
            reasoning_effort=None,
            quantization=None,
            backend=None,
            profile="test",
            benchmark_version=None,
            jobs=2,
            run_wall_time_seconds=10.0,
        )
        assert meta.metadata_available["model_identity"] is True  # provider set
        assert meta.metadata_available["runtime"] is True  # profile set
        assert meta.metadata_available["timing"] is True  # run_wall_time_seconds set
        assert meta.metadata_available["hardware"] is True  # cpu_info from system

    def test_markers_false_when_empty(self):
        """Availability markers are False when no data in that category."""
        meta = RunLedgerMetadata()
        avail = meta.metadata_available
        # All markers default to not-populated.
        assert avail == {}
        # from_metadata_dict preserves empty markers.
        restored = RunLedgerMetadata.from_metadata_dict({"metadata_available": {}})
        assert restored.metadata_available == {}


# ── Run-level wall time integration tests ─────────────────────────────────


class TestRunWallTime:
    def test_run_wall_time_in_result(self, tmp_path, monkeypatch):
        """run_benchmark includes run_wall_time_seconds in metadata."""
        from hermesbench.adapters.base import AgentRun

        class FastAdapter:
            def run_task(self, task, workdir, hidden_dir=None):
                (workdir / "done.txt").write_text("ok")
                return AgentRun(status="completed", transcript="done", tool_calls=0)

        monkeypatch.setattr(
            "hermesbench.runner.get_adapter",
            lambda *args, **kwargs: FastAdapter(),
        )

        # Create a minimal task pack.
        task_root = tmp_path / "tasks"
        _write_minimal_task_pack(task_root)
        monkeypatch.setattr("hermesbench.runner.ROOT", tmp_path)

        result_path = run_benchmark(
            agent="hermes",
            suite="natural-tools-dev",
            output_dir=tmp_path / "results",
            task_root=task_root,
        )
        data = json.loads(result_path.read_text())
        meta = data["metadata"]
        assert "run_wall_time_seconds" in meta
        assert isinstance(meta["run_wall_time_seconds"], (int, float))
        assert meta["run_wall_time_seconds"] > 0

    def test_run_wall_time_exceeds_sum_task_times(self, tmp_path, monkeypatch):
        """Run wall time should be >= the sum of task times for sequential runs."""
        from hermesbench.adapters.base import AgentRun
        import time as _time

        class SlowAdapter:
            def run_task(self, task, workdir, hidden_dir=None):
                _time.sleep(0.1)
                (workdir / "done.txt").write_text("ok")
                return AgentRun(status="completed", transcript="done", tool_calls=0)

        monkeypatch.setattr(
            "hermesbench.runner.get_adapter",
            lambda *args, **kwargs: SlowAdapter(),
        )

        task_root = tmp_path / "tasks"
        _write_minimal_task_pack(task_root, count=2)
        monkeypatch.setattr("hermesbench.runner.ROOT", tmp_path)

        result_path = run_benchmark(
            agent="hermes",
            suite="natural-tools-dev",
            output_dir=tmp_path / "results",
            task_root=task_root,
            jobs=1,  # sequential
        )
        data = json.loads(result_path.read_text())
        run_wall = data["metadata"]["run_wall_time_seconds"]
        task_sum = sum(r["wall_time_seconds"] for r in data["results"])
        # Run wall time should be at least the sum of task times (could be
        # slightly more due to overhead).
        assert run_wall >= task_sum, (
            f"run wall time {run_wall} < sum of task times {task_sum}"
        )

    def test_run_wall_time_with_parallel_tasks(self, tmp_path, monkeypatch):
        """With parallelism, run wall time should be less than sum of task times.

        Uses a threading.Barrier to prove parallel execution deterministically
        instead of timing-sensitive real sleeps. All 3 tasks wait on the barrier
        before returning — if they ran sequentially the first would time out.
        A tiny bounded computation (counting loop) after the barrier ensures
        wall-time measurements are reliably non-zero at 3-decimal precision
        without introducing timing flakiness.
        """
        from hermesbench.adapters.base import AgentRun

        barrier = threading.Barrier(3, timeout=5)  # 3 tasks, all must arrive

        class SyncAdapter:
            def run_task(self, task, workdir, hidden_dir=None):
                barrier.wait()  # proves parallel execution
                # Bounded CPU work so wall_time_seconds is reliably > 0
                # even at 3-decimal rounding, without real I/O sleeps.
                _ = sum(i * i for i in range(250_000))
                (workdir / "done.txt").write_text("ok")
                return AgentRun(status="completed", transcript="done", tool_calls=0)

        monkeypatch.setattr(
            "hermesbench.runner.get_adapter",
            lambda *args, **kwargs: SyncAdapter(),
        )

        task_root = tmp_path / "tasks"
        _write_minimal_task_pack(task_root, count=3)
        monkeypatch.setattr("hermesbench.runner.ROOT", tmp_path)

        result_path = run_benchmark(
            agent="hermes",
            suite="natural-tools-dev",
            output_dir=tmp_path / "results",
            task_root=task_root,
            jobs=3,  # parallel
        )
        data = json.loads(result_path.read_text())
        run_wall = data["metadata"]["run_wall_time_seconds"]
        task_sum = sum(r["wall_time_seconds"] for r in data["results"])
        # All tasks overlap (barrier synchronisation), so run wall time ≈
        # max(task_time) which must be < sum of individual task times.
        assert run_wall < task_sum, (
            f"parallel run wall time {run_wall} >= sum of task times {task_sum} — "
            "expected parallelism to reduce wall time"
        )


# ── Helpers ───────────────────────────────────────────────────────────────


def _write_minimal_task_pack(root: Path, count: int = 1) -> None:
    """Write a minimal task pack for test runs."""
    suite = root / "natural-tools-dev"
    suite.mkdir(parents=True)
    manifest_lines = [
        "suites:",
        "  natural-tools-dev:",
        "    version: test",
        "    tasks:",
    ]
    for i in range(count):
        tid = f"ledger-test-task-{i}"
        manifest_lines.extend([
            f"    - id: {tid}",
            f"      path: natural-tools-dev/{tid}.md",
            "      category: natural-tool-use",
            "      visibility: public",
        ])
        (suite / f"{tid}.md").write_text(f"""---
id: {tid}
title: Ledger test {i}
category: natural-tool-use
wave: test
visibility: public
created_at: 2026-07-10
freshness_window: test
expected_human_minutes: 1
difficulty: easy
required_toolsets:
- terminal
grading_type: deterministic
timeout_seconds: 10
contamination_notes: test fixture
safety_notes: local only
---

## Prompt
Create done.txt.

## Expected artifacts
- done.txt

## Deterministic checks
- artifact_exists: done.txt

## Hidden checks
- none

## Cleanup
rm -f done.txt
""")
    (root / "manifest.yaml").write_text("\n".join(manifest_lines) + "\n")
