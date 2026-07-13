"""Edge-case tests for _resolve_jobs (runner.py) and timestamp parsing (scoring.py).

These tests document the intended behaviour of the implementation for
non-happy-path inputs that Issue #4 H5/H6 flagged as potential gaps.

Key audit findings as they apply to the actual code:

H5 — _resolve_jobs edge cases
  - ``jobs=0`` and negative int values are clamped to 1 (defensive; not a bug).
  - ``jobs="0"`` (string from env) is parsed to ``int("0")`` → 0 → clamped to 1.
  - ``jobs=""`` (empty string) is treated as ``"auto"`` (same as the auto keyword).
  - ``task_count=0`` returns 1 because of the early-return guard ``if task_count <= 1``
    (effectively unreachable in ``run_benchmark`` because it raises ``ValueError``
    on an empty task list before reaching ``_resolve_jobs``).
  - Invalid strings (e.g. ``"abc"``) propagate ``ValueError`` from ``int()``.

  These are not correctness bugs — the clamping is a deliberate safety
  guard.  The following tests document the existing behaviour.

H6 — _parse_iso_timestamp / _run_duration_seconds edge cases
  - **Real bug found and fixed**: Z-suffixed timestamps (``"2026-01-01T00:00:00Z"``)
    were returned as *naive* datetimes (``s.rstrip("Z")`` strips the suffix before
    parsing).  Timestamps with explicit offsets (``"+00:00"``) were returned as
    *aware* datetimes.  When ``_run_duration_seconds`` subtracted a naive from an
    aware datetime, Python raised ``TypeError: can't subtract offset-naive and
    offset-aware datetimes``.

  - **Fix**: after successfully parsing a Z-suffixed timestamp, the resulting
    ``datetime`` is converted to timezone-aware UTC via
    ``dt.replace(tzinfo=timezone.utc)``.

  - Other edge cases (empty string, non-string, invalid formats, fractional
    seconds with &lt;6 digits, space-separated) are documented as not-a-bug.
"""

from __future__ import annotations

import json
import os
import statistics

from datetime import datetime, timezone
from pathlib import Path

import pytest

from hermesbench.runner import _resolve_jobs, _safe_command
from hermesbench.scoring import _parse_iso_timestamp, _run_duration_seconds, aggregate


# ═══════════════════════════════════════════════════════════════════════
#  _resolve_jobs edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestResolveJobs:
    """Intended behaviour of ``_resolve_jobs`` for all input shapes.

    Note: ``task_count=0`` is practically unreachable from ``run_benchmark``
    because the runner raises ``ValueError("no tasks selected")`` before
    calling ``_resolve_jobs``.  We test it here for completeness.
    """

    def test_normal_case(self) -> None:
        """jobs=4 with 10 tasks → 4."""
        assert _resolve_jobs(4, task_count=10) == 4

    def test_jobs_exceeds_task_count(self) -> None:
        """jobs=100 with 3 tasks → clamped to 3."""
        assert _resolve_jobs(100, task_count=3) == 3

    def test_jobs_zero_clamped_to_one(self) -> None:
        """jobs=0 is clamped to 1 (defensive, not a bug)."""
        assert _resolve_jobs(0, task_count=5) == 1

    def test_jobs_negative_clamped_to_one(self) -> None:
        """jobs=-1 is clamped to 1."""
        assert _resolve_jobs(-1, task_count=5) == 1

    def test_jobs_large_negative_clamped_to_one(self) -> None:
        """jobs=-999 is clamped to 1."""
        assert _resolve_jobs(-999, task_count=5) == 1

    def test_string_zero_clamped_to_one(self) -> None:
        """jobs="0" (string from env) → 0 → clamped to 1."""
        assert _resolve_jobs("0", task_count=5) == 1

    def test_string_one_works(self) -> None:
        """jobs="1" → 1."""
        assert _resolve_jobs("1", task_count=5) == 1

    def test_empty_string_is_auto(self) -> None:
        """jobs="" → treated as 'auto' → max(1, min(task_count, cpu_count))."""
        result = _resolve_jobs("", task_count=10)
        expected = max(1, min(10, os.cpu_count() or 1))
        assert result == expected

    def test_auto_string(self) -> None:
        """jobs="auto" → auto-detect."""
        result = _resolve_jobs("auto", task_count=8)
        expected = max(1, min(8, os.cpu_count() or 1))
        assert result == expected

    def test_auto_case_insensitive(self) -> None:
        """jobs="AUTO" → auto-detect."""
        result = _resolve_jobs("AUTO", task_count=5)
        expected = max(1, min(5, os.cpu_count() or 1))
        assert result == expected

    def test_none_without_env_var_uses_auto(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """jobs=None with no HERMESBENCH_JOBS env → auto-detect."""
        monkeypatch.delenv("HERMESBENCH_JOBS", raising=False)
        result = _resolve_jobs(None, task_count=6)
        expected = max(1, min(6, os.cpu_count() or 1))
        assert result == expected

    def test_none_with_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """jobs=None with HERMESBENCH_JOBS=8 → 8 (clamped to task_count)."""
        monkeypatch.setenv("HERMESBENCH_JOBS", "8")
        assert _resolve_jobs(None, task_count=10) == 8

    def test_none_with_env_var_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """jobs=None with HERMESBENCH_JOBS=0 → 0 → clamped to 1."""
        monkeypatch.setenv("HERMESBENCH_JOBS", "0")
        assert _resolve_jobs(None, task_count=5) == 1

    def test_single_task_returns_one(self) -> None:
        """task_count <= 1 always returns 1 regardless of jobs value."""
        assert _resolve_jobs(99, task_count=1) == 1
        assert _resolve_jobs(0, task_count=1) == 1
        assert _resolve_jobs(-5, task_count=1) == 1
        assert _resolve_jobs("auto", task_count=1) == 1
        assert _resolve_jobs(None, task_count=1) == 1

    def test_zero_tasks_returns_one(self) -> None:
        """task_count=0 returns 1 (the early-return guard)."""
        assert _resolve_jobs(4, task_count=0) == 1
        assert _resolve_jobs(0, task_count=0) == 1

    def test_invalid_string_raises(self) -> None:
        """Non-numeric string like "abc" propagates ValueError from int()."""
        with pytest.raises(ValueError, match="invalid literal for int"):
            _resolve_jobs("abc", task_count=5)


# ═══════════════════════════════════════════════════════════════════════
#  _parse_iso_timestamp edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestParseIsoTimestamp:
    """Intended behaviour of ``_parse_iso_timestamp``.

    Key correctness fix: Z-suffixed timestamps are now returned as
    timezone-aware UTC (not naive) so they can be safely combined with
    offset-aware timestamps in ``_run_duration_seconds``.
    """

    def test_z_suffix_is_aware_utc(self) -> None:
        """Z-suffixed → aware UTC datetime, not naive."""
        dt = _parse_iso_timestamp("2026-07-10T00:00:00Z")
        assert dt is not None
        assert dt.tzinfo is timezone.utc
        assert dt == datetime(2026, 7, 10, 0, 0, 0, tzinfo=timezone.utc)

    def test_z_suffix_with_microseconds_is_aware_utc(self) -> None:
        """Z-suffixed with fractional seconds → aware UTC."""
        dt = _parse_iso_timestamp("2026-07-10T12:30:00.123456Z")
        assert dt is not None
        assert dt.tzinfo is timezone.utc
        assert dt == datetime(2026, 7, 10, 12, 30, 0, 123456, tzinfo=timezone.utc)

    def test_z_suffix_fractional_short(self) -> None:
        """Z-suffixed with 1-digit fractional (.1) → parsed correctly."""
        dt = _parse_iso_timestamp("2026-07-10T12:30:00.1Z")
        assert dt is not None
        assert dt.tzinfo is timezone.utc
        # .1 second = 100000 microseconds
        assert dt.microsecond == 100000

    def test_positive_offset_aware(self) -> None:
        """+00:00 offset → aware datetime."""
        dt = _parse_iso_timestamp("2026-07-10T00:00:00+00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_positive_offset_with_microseconds(self) -> None:
        """+00:00 offset with micros → aware datetime."""
        dt = _parse_iso_timestamp("2026-07-10T00:00:00.123456+00:00")
        assert dt is not None
        assert dt.tzinfo is not None

    def test_negative_offset(self) -> None:
        """Negative UTC offset (-05:00) → correct tzinfo."""
        dt = _parse_iso_timestamp("2026-07-10T00:00:00-05:00")
        assert dt is not None
        assert dt.tzinfo is not None
        # Offset from UTC should be -5 hours = -18000 seconds
        assert dt.utcoffset() is not None
        assert dt.utcoffset().total_seconds() == -18000.0

    def test_naive_no_tz(self) -> None:
        """No timezone indicator → naive datetime."""
        dt = _parse_iso_timestamp("2026-07-10T00:00:00")
        assert dt is not None
        assert dt.tzinfo is None

    def test_naive_with_microseconds(self) -> None:
        """Naive with fractional seconds."""
        dt = _parse_iso_timestamp("2026-07-10T12:30:00.500")
        assert dt is not None
        assert dt.tzinfo is None
        assert dt.microsecond == 500000

    def test_space_separator(self) -> None:
        """Space instead of T → parsed."""
        dt = _parse_iso_timestamp("2026-07-10 00:00:00")
        assert dt is not None
        assert dt.tzinfo is None

    def test_empty_string_returns_none(self) -> None:
        """Empty string → None."""
        assert _parse_iso_timestamp("") is None

    def test_non_string_returns_none(self) -> None:
        """Non-string input (e.g. int, None) → None."""
        assert _parse_iso_timestamp(12345) is None  # type: ignore[arg-type]
        assert _parse_iso_timestamp(None) is None  # type: ignore[arg-type]

    def test_invalid_format_returns_none(self) -> None:
        """Garbage string → None (no crash)."""
        assert _parse_iso_timestamp("not-a-timestamp") is None

    def test_unix_timestamp_returns_none(self) -> None:
        """Numeric-looking but non-ISO → None."""
        assert _parse_iso_timestamp("1712345678") is None

    def test_standard_format_produced_by_runner(self) -> None:
        """Format matching ``datetime.now(timezone.utc).isoformat()``."""
        dt = _parse_iso_timestamp("2026-07-11T12:34:56.789012+00:00")
        assert dt is not None
        assert dt.tzinfo is not None
        assert dt.year == 2026
        assert dt.month == 7
        assert dt.day == 11
        assert dt.hour == 12
        assert dt.minute == 34
        assert dt.second == 56
        assert dt.microsecond == 789012


# ═══════════════════════════════════════════════════════════════════════
#  _run_duration_seconds edge cases
# ═══════════════════════════════════════════════════════════════════════

class TestRunDurationSeconds:
    """Intended behaviour of ``_run_duration_seconds``.

    The core fix ensures that mixed naive/aware inputs no longer crash.
    """

    def test_both_z_suffix(self) -> None:
        """Both Z-suffixed → works (both now aware UTC)."""
        dur = _run_duration_seconds(
            "2026-07-10T00:00:00Z",
            "2026-07-10T00:05:30Z",
        )
        assert dur is not None
        assert dur == pytest.approx(330.0)

    def test_both_aware_offset(self) -> None:
        """Both with +00:00 offset → works."""
        dur = _run_duration_seconds(
            "2026-07-10T00:00:00+00:00",
            "2026-07-10T00:05:30+00:00",
        )
        assert dur is not None
        assert dur == pytest.approx(330.0)

    def test_mixed_z_and_offset(self) -> None:
        """One Z-suffixed, one with +00:00 → was a TypeError before the fix."""
        dur = _run_duration_seconds(
            "2026-07-10T00:00:00Z",
            "2026-07-10T00:05:30+00:00",
        )
        assert dur is not None
        assert dur == pytest.approx(330.0)

    def test_mixed_offset_and_z(self) -> None:
        """One offset, one Z-suffixed (reversed order)."""
        dur = _run_duration_seconds(
            "2026-07-10T00:00:00+00:00",
            "2026-07-10T00:05:30Z",
        )
        assert dur is not None
        assert dur == pytest.approx(330.0)

    def test_different_non_utc_offsets(self) -> None:
        """Different non-UTC offsets are compared on the absolute timeline."""
        dur = _run_duration_seconds(
            "2026-07-10T12:00:00+02:00",
            "2026-07-10T05:30:00-05:00",
        )
        assert dur is not None
        assert dur == pytest.approx(1800.0)

    def test_negative_offset(self) -> None:
        """Both with negative offset → works."""
        dur = _run_duration_seconds(
            "2026-07-10T00:00:00-05:00",
            "2026-07-10T00:05:30-05:00",
        )
        assert dur is not None
        assert dur == pytest.approx(330.0)

    def test_same_timestamp_zero_duration(self) -> None:
        """start == end → 0.0."""
        dur = _run_duration_seconds(
            "2026-07-10T12:00:00Z",
            "2026-07-10T12:00:00Z",
        )
        assert dur is not None
        assert dur == pytest.approx(0.0)

    def test_fractional_seconds(self) -> None:
        """Fractional seconds preserved."""
        dur = _run_duration_seconds(
            "2026-01-15T10:30:00Z",
            "2026-01-15T10:35:15.500Z",
        )
        assert dur is not None
        assert dur == pytest.approx(315.5)

    def test_empty_start_is_none(self) -> None:
        """Empty started_at → None."""
        assert _run_duration_seconds("", "2026-07-10T00:05:00Z") is None

    def test_empty_completed_is_none(self) -> None:
        """Empty completed_at → None."""
        assert _run_duration_seconds("2026-07-10T00:00:00Z", "") is None

    def test_both_empty_is_none(self) -> None:
        """Both empty → None."""
        assert _run_duration_seconds("", "") is None

    def test_unparseable_is_none(self) -> None:
        """Unparseable timestamps → None (no crash)."""
        assert _run_duration_seconds("s", "c") is None


# ═══════════════════════════════════════════════════════════════════════
#  aggregate integration — mixed timestamp formats
# ═══════════════════════════════════════════════════════════════════════

class TestAggregateTimestampFormats:
    """``aggregate()`` must tolerate any combination of ISO timestamp formats
    without crashing, and produce sensible ``run_duration_seconds``.
    """

    TIMESTAMP_COMBOS = [
        # (started_at, completed_at, expected_duration)
        ("2026-07-10T00:00:00Z", "2026-07-10T00:05:30Z", 330.0),
        ("2026-07-10T00:00:00+00:00", "2026-07-10T00:05:30+00:00", 330.0),
        ("2026-07-10T00:00:00Z", "2026-07-10T00:05:30+00:00", 330.0),
        ("2026-07-10T00:00:00+00:00", "2026-07-10T00:05:30Z", 330.0),
        ("2026-07-10T00:00:00", "2026-07-10T00:05:30", 330.0),
        ("2026-07-10 00:00:00", "2026-07-10 00:05:30", 330.0),
        ("2026-07-10T00:00:00.000Z", "2026-07-10T00:05:30.000Z", 330.0),
        ("2026-07-10T12:00:00.1Z", "2026-07-10T12:05:30.2Z", 330.1),
        ("2026-07-10T00:00:00+02:00", "2026-07-10T00:05:30-05:00", 330.0 + 7*3600),  # mixed offsets (+02:00 to -05:00 = 7h diff)
        ("s", "c", None),
    ]

    @pytest.mark.parametrize(
        ("started_at", "completed_at", "expected"),
        TIMESTAMP_COMBOS,
        ids=[
            "both-Z",
            "both-offset",
            "Z-start-offset-end",
            "offset-start-Z-end",
            "both-naive-no-Z",
            "space-separator",
            "both-Z-with-micros",
            "short-fractional-Z",
            "mixed-offsets",
            "unparseable",
        ],
    )
    def test_aggregate_run_duration(
        self, tmp_path: Path, started_at: str, completed_at: str, expected: float | None
    ) -> None:
        """aggregate() does not crash on any timestamp format combination."""
        result = tmp_path / "result.json"
        result.write_text(
            json.dumps(
                {
                    "schema_version": "hermesbench.result.v1",
                    "run_id": "ts-format-test",
                    "suite": "natural-tools-dev",
                    "agent": "hermes",
                    "model": "m",
                    "started_at": started_at,
                    "completed_at": completed_at,
                    "metadata": {},
                    "results": [
                        {
                            "task_id": "t1",
                            "category": "cat",
                            "status": "passed",
                            "score": 1.0,
                            "passed": True,
                            "wall_time_seconds": 10,
                        },
                    ],
                }
            )
        )
        score = aggregate(result)
        if expected is not None:
            assert score["run_duration_seconds"] == pytest.approx(expected)
            assert score["tasks_per_second"] == pytest.approx(1.0 / expected)
        else:
            assert score["run_duration_seconds"] is None
            assert score["tasks_per_second"] is None


class TestAggregateEdgeCases:
    """Additional aggregate edge conditions related to scoring/runner gaps."""

    def test_aggregate_empty_results_does_not_crash(self, tmp_path: Path) -> None:
        """Empty results list does not cause unhandled division-by-zero in aggregate.

        (The runner never produces empty results, but the function should cope.)
        """
        result = tmp_path / "result.json"
        result.write_text(
            json.dumps(
                {
                    "schema_version": "hermesbench.result.v1",
                    "run_id": "empty-results",
                    "suite": "natural-tools-dev",
                    "agent": "hermes",
                    "model": "m",
                    "started_at": "2026-07-10T00:00:00Z",
                    "completed_at": "2026-07-10T00:05:00Z",
                    "metadata": {},
                    "results": [],
                }
            )
        )
        # Should not crash; some fields may be 0 or None.
        score = aggregate(result)
        assert score["overall_score"] == 0.0
        assert score["task_count"] == 0
        assert score["scored_task_count"] == 0
        assert score["run_duration_seconds"] == 300.0

    def test_aggregate_all_environment_skips(self, tmp_path: Path) -> None:
        """All tasks are environment_skipped → scored_task_count=0 but no crash."""
        result = tmp_path / "result.json"
        result.write_text(
            json.dumps(
                {
                    "schema_version": "hermesbench.result.v1",
                    "run_id": "all-skip",
                    "suite": "natural-tools-dev",
                    "agent": "hermes",
                    "model": "m",
                    "started_at": "s",
                    "completed_at": "c",
                    "metadata": {},
                    "results": [
                        {
                            "task_id": "t1",
                            "category": "nat",
                            "status": "environment_skipped",
                            "score": 0.0,
                            "passed": False,
                            "wall_time_seconds": 0.0,
                            "environment_skip": True,
                        },
                    ],
                }
            )
        )
        score = aggregate(result)
        assert score["scored_task_count"] == 0
        assert score["task_count"] == 1
        assert score["overall_score"] == 0.0
        assert score["capability_evaluable"] is True

    def test_aggregate_with_cost_fields(self, tmp_path: Path) -> None:
        """cost fields are handled correctly (null-safe)."""
        result = tmp_path / "result.json"
        result.write_text(
            json.dumps(
                {
                    "schema_version": "hermesbench.result.v1",
                    "run_id": "cost-test",
                    "suite": "natural-tools-dev",
                    "agent": "hermes",
                    "model": "m",
                    "started_at": "s",
                    "completed_at": "c",
                    "metadata": {},
                    "results": [
                        {
                            "task_id": "t1",
                            "category": "cat",
                            "status": "passed",
                            "score": 1.0,
                            "passed": True,
                            "wall_time_seconds": 10,
                            "cost_usd": 0.01,
                        },
                        {
                            "task_id": "t2",
                            "category": "cat",
                            "status": "failed",
                            "score": 0.0,
                            "passed": False,
                            "wall_time_seconds": 20,
                            "cost_usd": 0.02,
                        },
                        {
                            "task_id": "t3",
                            "category": "cat",
                            "status": "passed",
                            "score": 1.0,
                            "passed": True,
                            "wall_time_seconds": 15,
                        },
                    ],
                }
            )
        )
        score = aggregate(result)
        assert score["cost_usd"] == 0.03
        assert score["total_cost_usd"] == 0.03
        # Per-success metric preserves the cost attributed to successful tasks.
        assert score["cost_per_successful_task_usd"] == 0.005
        # cost_per_task: total cost / 3 tasks
        assert score["cost_per_task_usd"] == pytest.approx(0.01)
        # score_per_dollar: (overall_score * 100 / total_cost) = (2/3 * 100 / 0.03) = 2222.22...
        assert score["score_per_dollar"] == pytest.approx(2222.222222222222)

    def test_aggregate_no_cost_at_all(self, tmp_path: Path) -> None:
        """No cost data → all cost fields are None."""
        result = tmp_path / "result.json"
        result.write_text(
            json.dumps(
                {
                    "schema_version": "hermesbench.result.v1",
                    "run_id": "no-cost",
                    "suite": "natural-tools-dev",
                    "agent": "hermes",
                    "model": "m",
                    "started_at": "s",
                    "completed_at": "c",
                    "metadata": {},
                    "results": [
                        {
                            "task_id": "t1",
                            "category": "cat",
                            "status": "passed",
                            "score": 1.0,
                            "passed": True,
                            "wall_time_seconds": 10,
                        },
                    ],
                }
            )
        )
        score = aggregate(result)
        assert score["cost_usd"] is None
        assert score["cost_per_task_usd"] is None
        assert score["cost_per_successful_task_usd"] is None
        assert score["score_per_dollar"] is None

    def test_aggregate_wall_time_stats(self, tmp_path: Path) -> None:
        """Wall-time percentile and summary stats are computed correctly."""
        result = tmp_path / "result.json"
        result.write_text(
            json.dumps(
                {
                    "schema_version": "hermesbench.result.v1",
                    "run_id": "wall-time",
                    "suite": "natural-tools-dev",
                    "agent": "hermes",
                    "model": "m",
                    "started_at": "s",
                    "completed_at": "c",
                    "metadata": {},
                    "results": [
                        {
                            "task_id": f"t{i}",
                            "category": "cat",
                            "status": "passed" if i < 3 else "failed",
                            "score": 1.0 if i < 3 else 0.0,
                            "passed": i < 3,
                            "wall_time_seconds": float(v),
                        }
                        for i, v in enumerate([1.0, 2.0, 3.0, 4.0, 5.0])
                    ],
                }
            )
        )
        score = aggregate(result)
        assert score["median_wall_time_seconds"] == 3.0
        assert score["mean_wall_time_seconds"] == 3.0
        assert score["min_wall_time_seconds"] == 1.0
        assert score["max_wall_time_seconds"] == 5.0
        assert score["sum_wall_time_seconds"] == 15.0
        assert score["total_execution_time_seconds"] == 15.0

    def test_aggregate_zero_success_cost_no_crash(self, tmp_path: Path) -> None:
        """When all tasks have cost=0, division is safe."""
        result = tmp_path / "result.json"
        result.write_text(
            json.dumps(
                {
                    "schema_version": "hermesbench.result.v1",
                    "run_id": "zero-cost",
                    "suite": "natural-tools-dev",
                    "agent": "hermes",
                    "model": "m",
                    "started_at": "s",
                    "completed_at": "c",
                    "metadata": {},
                    "results": [
                        {
                            "task_id": "t1",
                            "category": "cat",
                            "status": "passed",
                            "score": 1.0,
                            "passed": True,
                            "wall_time_seconds": 10,
                            "cost_usd": 0.0,
                        },
                    ],
                }
            )
        )
        score = aggregate(result)
        assert score["cost_usd"] == 0.0
        assert score["cost_per_task_usd"] == 0.0
        assert score["cost_per_successful_task_usd"] == 0.0


# ═══════════════════════════════════════════════════════════════════════
#  _safe_command redaction edge cases
# ═══════════════════════════════════════════════════════════════════════


class TestSafeCommand:
    """Focused regression tests for ``_safe_command`` credential redaction.

    Tests only edge cases the implementation actually supports, based on
    ``SENSITIVE_COMMAND_RE`` at runner.py:30-32.
    """

    def test_none_input(self) -> None:
        """None → None (no crash)."""
        assert _safe_command(None) is None

    def test_empty_string(self) -> None:
        """Empty string → unchanged empty string."""
        assert _safe_command("") == ""

    def test_no_credentials_unchanged(self) -> None:
        """Plain command with no sensitive keywords is returned unchanged."""
        cmd = "ls -la /tmp"
        assert _safe_command(cmd) == cmd

    def test_api_key_equal_separator(self) -> None:
        """api_key=value redacts the value after ``=``."""
        result = _safe_command("api_key=abc123")
        assert result == "api_key=[REDACTED]"

    def test_token_colon_separator(self) -> None:
        """token:value redacts the value after ``:``."""
        result = _safe_command("token:my-secret-token")
        assert result == "token:[REDACTED]"

    def test_secret_whitespace_separator(self) -> None:
        """secret value (whitespace separator) redacts the value."""
        result = _safe_command("secret mypass")
        assert result == "secret [REDACTED]"

    def test_bearer_jwt(self) -> None:
        """``Bearer <token>`` outside ``authorization:`` header redacts the token,
        preserving the ``Bearer `` prefix via the ``\\bBearer\\s+`` branch."""
        result = _safe_command(
            "--header 'Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.dkWrCQ'"
        )
        assert "Bearer " in result  # prefix preserved
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "[REDACTED]" in result

    def test_case_insensitive(self) -> None:
        """All keywords match case-insensitively."""
        result = _safe_command("API_KEY=foo TOKEN=bar SECRET=baz")
        assert result == "API_KEY=[REDACTED] TOKEN=[REDACTED] SECRET=[REDACTED]"

    def test_multiple_credential_types(self) -> None:
        """Multiple credential keywords in one command are all redacted."""
        result = _safe_command(
            "hermes --api-key=abc --token=def --secret=ghi --password=jkl"
        )
        assert "abc" not in result
        assert "def" not in result
        assert "ghi" not in result
        assert "jkl" not in result
        assert all(kw in result for kw in ("--api-key=", "--token=", "--secret=", "--password="))
        assert result.count("[REDACTED]") == 4

    def test_env_var_export_form(self) -> None:
        """``export PASSWORD=abc123`` redacts the value."""
        result = _safe_command("export PASSWORD=abc123")
        assert result == "export PASSWORD=[REDACTED]"

    def test_hyphenated_and_underscored(self) -> None:
        """api-key and api_key both redact (``[_-]?`` in pattern)."""
        r1 = _safe_command("--api-key=mykey")
        r2 = _safe_command("--api_key=mykey")
        r3 = _safe_command("--apikey=mykey")
        assert r1 == "--api-key=[REDACTED]"
        assert r2 == "--api_key=[REDACTED]"
        assert r3 == "--apikey=[REDACTED]"

    def test_comma_terminated_value(self) -> None:
        """Redaction stops at comma (``[^\\s,]+``), so the comma is preserved."""
        result = _safe_command("api_key=val1,other")
        assert result == "api_key=[REDACTED],other"

    def test_password_and_credential_keywords(self) -> None:
        """password= and credential= are redacted."""
        result = _safe_command("credential=admin password=hunter2")
        assert result == "credential=[REDACTED] password=[REDACTED]"


# ═══════════════════════════════════════════════════════════════════════
#  aggregate — reasoning_effort preservation
# ═══════════════════════════════════════════════════════════════════════


class TestAggregateReasoningEffort:
    """``aggregate()`` must preserve ``reasoning_effort`` from metadata."""

    _BASE_RESULT: dict = {
        "schema_version": "hermesbench.result.v1",
        "run_id": "re-test",
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
                "score": 1.0,
                "passed": True,
                "wall_time_seconds": 10,
            },
        ],
    }

    def test_reasoning_effort_preserved(self, tmp_path: Path) -> None:
        """``aggregate()`` returns ``reasoning_effort`` from metadata unchanged."""
        data = dict(self._BASE_RESULT)
        data["metadata"] = {"reasoning_effort": "high"}
        path = tmp_path / "result.json"
        path.write_text(json.dumps(data))
        score = aggregate(path)
        assert score["reasoning_effort"] == "high"

    def test_reasoning_effort_none_when_missing(self, tmp_path: Path) -> None:
        """No ``reasoning_effort`` in metadata → ``None`` in score."""
        data = dict(self._BASE_RESULT)
        data["metadata"] = {}
        path = tmp_path / "result.json"
        path.write_text(json.dumps(data))
        score = aggregate(path)
        assert score["reasoning_effort"] is None

    def test_reasoning_effort_null_in_metadata(self, tmp_path: Path) -> None:
        """``reasoning_effort`` explicitly ``null`` → ``None`` in score."""
        data = dict(self._BASE_RESULT)
        data["metadata"] = {"reasoning_effort": None}
        path = tmp_path / "result.json"
        path.write_text(json.dumps(data))
        score = aggregate(path)
        assert score["reasoning_effort"] is None

    def test_reasoning_effort_with_different_values(self, tmp_path: Path) -> None:
        """Different reasoning_effort values flow through unchanged."""
        for effort in ("low", "medium", "high", "max", "some-custom-value"):
            data = dict(self._BASE_RESULT)
            data["metadata"] = {"reasoning_effort": effort}
            path = tmp_path / "result.json"
            path.write_text(json.dumps(data))
            score = aggregate(path)
            assert score["reasoning_effort"] == effort
