from __future__ import annotations
import json
from pathlib import Path
import subprocess

import pytest

from scripts.generate_website_data import _enhance, build_data, is_official_archive_source
from hermesbench.submissions import make_submission_payload
from hermesbench.tasks import discover_tasks, parse_task_markdown


def _result(path: Path, run_id="r1", official=False, agent="agent"):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": "hermesbench.result.v1",
        "run_id": run_id,
        "suite": "natural-tools-dev",
        "agent": agent,
        "model": "model",
        "started_at": "s",
        "completed_at": "c",
        "metadata": {"official": official},
        "results": [
            {
                "task_id": "t1",
                "category": "natural-tool-use",
                "status": "passed",
                "score": 1.0,
                "passed": True,
                "wall_time_seconds": 1,
                "logs": {"transcript": "secret"},
            }
        ],
    }
    path.write_text(json.dumps(data))
    return path


def test_website_data_generated_from_results_and_splits(tmp_path):
    _result(tmp_path / "results/u/hermesbench-u.json", "u", False)
    _result(tmp_path / "results/u2/hermesbench-u2.json", "u2", False)
    _result(tmp_path / "results/o/hermesbench-o.json", "o", True)
    lb = build_data(tmp_path / "results", tmp_path / "out")
    data = json.loads(lb.read_text())
    assert data["official"][0]["run_id"] == "o"
    assert data["unofficial"][0]["classification"] == "unofficial"
    unofficial_summary = next(
        s for s in data["model_summaries"] if s["classification"] == "unofficial"
    )
    assert unofficial_summary["submission_count"] == 2
    assert unofficial_summary.keys() >= {
        "best_score_percentage",
        "average_score_percentage",
        "score_stddev",
        "score_ci95_low",
        "score_ci95_high",
        "best_submission_id",
    }


def test_website_data_accepts_reviewed_private_trial_aggregate(tmp_path, monkeypatch):
    import scripts.generate_website_data as generator

    monkeypatch.setattr(generator, "ROOT", tmp_path)
    archive = tmp_path / "official-runs" / "reviewed-aggregate"
    archive.mkdir(parents=True)
    (archive / "manifest.yaml").write_text("official: true\n")
    (archive / "aggregate.json").write_text(json.dumps({
        "schema_version": "hermesbench.trials.v1", "aggregate_id": "agg1",
        "agent": "hermes", "provider": "provider", "model": "model",
        "suite": "hermes-core-private",
        "benchmark_version": "hermes-core-v0.2-private-reviewed",
        "private_pack_id": "sha256:opaque", "runner_commit": "abc123",
        "trial_count": 3, "evaluable_trial_count": 3,
        "reviewed_task_count": 12, "excluded_probe_count": 1,
        "score_mean": 0.75, "score_stddev": 0.1,
        "score_min": 0.6, "score_max": 0.9,
        "perfect_trial_rate": 0.0, "capability_pass_rate": 0.0,
        "cost_telemetry_complete": True, "total_cost_usd": 0.25,
    }))

    leaderboard = generator.build_data(tmp_path / "results", tmp_path / "out")
    entry = json.loads(leaderboard.read_text())["entries"][0]
    detail = json.loads((tmp_path / "out" / "runs" / "agg1.json").read_text())
    assert entry["capability_evidence"] is True
    assert entry["source"] == "official-runs/reviewed-aggregate/aggregate.json"
    assert entry["task_count"] == 12
    assert entry["trial_count"] == 3
    assert detail["schema_version"] == "hermesbench.score.v1"
    assert detail["aggregate"]["schema_version"] == "hermesbench.trials.v1"
    assert detail["tasks"] == []


def test_website_value_metrics_require_complete_cost_telemetry():
    partial = _enhance({
        "overall_score": 0.5,
        "total_cost_usd": 0.25,
        "passed_task_count": 1,
        "cost_telemetry_status": "partial",
    })
    complete = _enhance({
        "overall_score": 0.5,
        "total_cost_usd": 0.25,
        "passed_task_count": 1,
        "cost_telemetry_status": "complete",
    })

    assert partial["value_score"] is None
    assert partial["cpst"] is None
    assert complete["value_score"] == 2.0
    assert complete["cpst"] == 0.25


def test_website_detail_strips_private_metadata_and_task_logs(tmp_path):
    path = tmp_path / "results/u/hermesbench-u.json"
    _result(path, "u", False)
    data = json.loads(path.read_text())
    data["metadata"].update({"api_key": "secret", "environment": "ci"})
    data["results"][0]["verification_evidence"] = ["private evidence"]
    path.write_text(json.dumps(data))

    build_data(tmp_path / "results", tmp_path / "out")
    detail = json.loads((tmp_path / "out/runs/u.json").read_text())
    assert "api_key" not in detail["metadata"]
    assert detail["metadata"]["environment"] == "ci"
    assert "logs" not in detail["tasks"][0]
    assert "verification_evidence" not in detail["tasks"][0]


def test_website_generator_removes_latest_result_output(tmp_path):
    _result(tmp_path / "results/u/hermesbench-u.json", "u", False)
    lb = build_data(tmp_path / "results", tmp_path / "out")
    assert not (tmp_path / "out" / "latest-result.json").exists()


def test_website_generator_omits_absolute_local_source_paths(tmp_path):
    """Unofficial results must not leak local filesystem paths via ``source``.

    The ``source`` field is only meaningful for official-run entries where it
    points to a canonical ``official-runs/<safe-segment>/...`` archive path
    within the repo.  For external/unofficial results the path is an absolute
    local filesystem path that must be stripped to avoid leaking CI runners'
    directory structures.
    """
    _result(tmp_path / "external-results/u/hermesbench-u.json", "u", False)

    lb = build_data(tmp_path / "external-results", tmp_path / "out")
    data = json.loads(lb.read_text())
    assert "source" not in data["entries"][0]


def test_website_generator_only_marks_reviewed_official_archives_as_capability_evidence(
    tmp_path, monkeypatch
):
    """Only entries under ``official-runs/<segment>/...`` are capability evidence.

    A result that declares ``official: true`` but lives under an arbitrary
    directory (e.g. ``results/local/...``) is *not* automatically capability
    evidence — it must live in the canonical ``official-runs/`` tree and pass
    ``is_official_archive_source``.  This prevents a submitter from marking an
    ad-hoc result as capability evidence by setting ``official: true`` in metadata.
    """
    import scripts.generate_website_data as generator

    monkeypatch.setattr(generator, "ROOT", tmp_path)
    _result(
        tmp_path / "official-runs/reviewed/hermesbench-reviewed.json",
        "reviewed",
        True,
        agent="hermes",
    )
    _result(
        tmp_path / "results/local/hermesbench-local.json", "local", True, agent="hermes"
    )
    lb = generator.build_data(tmp_path, tmp_path / "out")

    entries = {
        entry["run_id"]: entry for entry in json.loads(lb.read_text())["entries"]
    }
    assert entries["reviewed"]["capability_evidence"] is True
    assert (
        entries["reviewed"]["source"]
        == "official-runs/reviewed/hermesbench-reviewed.json"
    )
    assert entries["local"]["capability_evidence"] is False
    assert entries["local"]["evidence_class"] == "unofficial_submission"
    assert "source" not in entries["local"]


def test_official_archive_source_requires_a_canonical_posix_path():
    assert is_official_archive_source(
        "official-runs/reviewed/hermesbench-reviewed.json"
    )
    for source in [
        "official-runs/%2e%2e/result.json",
        "official-runs/run/result.json?x=1",
        "official-runs/run/result.json#fragment",
        "official-runs\\\\run\\\\result.json",
        "https://example.test/official-runs/run/result.json",
        "official-runs//run/result.json",
        "official-runs/./run/result.json",
        "official-runs/../run/result.json",
        "official-runs/run/../result.json",
        "official-runs/run",
    ]:
        assert not is_official_archive_source(source), source


def test_website_build_rejects_non_archive_and_traversal_sources(tmp_path):
    root = Path(__file__).resolve().parents[1]
    build = root / "website/build.js"
    website = tmp_path / "website"
    (website / "data").mkdir(parents=True)
    (website / "index.html").write_text("<main></main>")
    (website / "app.js").write_text("// test")
    (website / "index.css").write_text("/* test */")
    entry = {
        "run_id": "fixture",
        "agent": "agent",
        "suite": "test",
        "overall_score": 0.0,
        "schema_version": "hermesbench.score.v1",
        "data_status": "run_data",
        "capability_evidence": False,
        "display_notice": "not capability evidence",
        "evidence_class": "unofficial_submission",
    }
    for source in [
        "results/run.json",
        "artifacts/run.json",
        "official_runs/run.json",
        "official-runs/../run.json",
        "official-runs//run/result.json",
        "official-runs/%2e%2e/result.json",
        "official-runs/run/result.json?x=1",
        "official-runs/run/result.json#fragment",
        "official-runs\\\\run\\\\result.json",
        "https://example.test/official-runs/run/result.json",
    ]:
        bad = {**entry, "source": source}
        (website / "data/leaderboard.json").write_text(
            json.dumps({**entry, "entries": [bad], "official": [], "unofficial": [bad]})
        )
        result = subprocess.run(
            ["node", str(build)], cwd=website, text=True, capture_output=True
        )
        assert result.returncode != 0, source


def test_website_build_tolerates_empty_data(tmp_path):
    root = Path(__file__).resolve().parents[1]
    website = tmp_path / "website"
    (website / "data").mkdir(parents=True)
    (website / "index.html").write_text("<main></main>")
    (website / "app.js").write_text("// test")
    (website / "index.css").write_text("/* test */")

    result = subprocess.run(
        ["node", str(root / "website/build.js")],
        cwd=website,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0


def test_app_capability_guards_enforce_evidence_policy():
    """Exercise the frontend evidence policy through its exported behavior."""
    root = Path(__file__).resolve().parents[1]
    script = f"""
const {{ isCapabilityData, isCapabilityRun, normalizeApiToFrontendShape }} = require({str(root / 'website/app.js')!r});
const official = {{ run_id: 'official-1', official: true, evidence_class: 'official_evidence', capability_evidence: true, source: 'official-runs/run-1/result.json' }};
const normalized = normalizeApiToFrontendShape({{ entries: [official] }});
if (isCapabilityData(normalized)) throw new Error('live API data must not be capability evidence');
if (isCapabilityRun(normalized.entries[0])) throw new Error('normalized live API rows must not be capability evidence');
if (!isCapabilityData({{ data_status: 'run_data', capability_evidence: true }})) throw new Error('official data should be capability evidence');
if (isCapabilityData({{ data_status: 'no_data', capability_evidence: true }})) throw new Error('no-data state must not be capability evidence');
if (!isCapabilityRun(official)) throw new Error('official archived run should be a capability run');
if (isCapabilityRun({{ ...official, evidence_class: 'unofficial_submission' }})) throw new Error('unofficial run must not be a capability run');
"""
    result = subprocess.run(["node", "-e", script], cwd=root, text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_visible_suite_counts_match_the_manifest_contract():
    root = Path(__file__).resolve().parents[1]
    app = (root / "website/app.js").read_text()
    readme = (root / "README.md").read_text()

    from hermesbench.versions import BENCHMARK_VERSIONS

    core_count = BENCHMARK_VERSIONS["hermes-core-v0.1"]["task_count"]
    ext_count = BENCHMARK_VERSIONS["hermes-extended-v0.1"]["task_count"]
    total = core_count + ext_count

    assert f"total: {total}" in app
    assert f"hermesCore: {core_count}" in app
    assert f"hermesExtended: {ext_count}" in app
    assert f"| `hermes-core` | {core_count} |" in readme
    assert f"| `hermes-extended` | {ext_count} |" in readme


def _read_workflow(root, name):
    return (root / ".github/workflows" / name).read_text()


def _check_common_workflow_safety(wf_text, wf_name):
    """Assertions every self-hosted workflow must satisfy."""
    # Concurrency serialization across real-agent jobs
    assert "concurrency:" in wf_text, f"{wf_name}: missing concurrency"
    assert "hermesbench-realagent-" in wf_text, (
        f"{wf_name}: concurrency group must use hermesbench-realagent prefix"
    )
    # Unique run/job-specific smoke output directory
    assert "github.run_id" in wf_text and "github.job" in wf_text, (
        f"{wf_name}: smoke dir must include run_id and job for uniqueness"
    )
    assert "SMOKE_DIR" in wf_text, f"{wf_name}: smoke dir must use named variable"
    # Cleanup trap on smoke artifacts
    assert "Cleanup smoke artifacts" in wf_text, (
        f"{wf_name}: missing cleanup step for smoke artifacts"
    )
    assert "if: always()" in wf_text, (
        f"{wf_name}: cleanup must run always()"
    )
    assert "rm -rf" in wf_text, f"{wf_name}: cleanup must remove smoke directory"
    # Hermes version recording after install
    assert "Record Hermes version pre-install" in wf_text, (
        f"{wf_name}: must record Hermes version pre-install"
    )
    assert "hermes --version" in wf_text or "hermes version" in wf_text, (
        f"{wf_name}: must run hermes version command"
    )
    # Clear profile/preflight failures
    assert "Missing local Hermes profile" in wf_text, (
        f"{wf_name}: profile check must have actionable error message"
    )
    assert "hermes profile create hermesbench" in wf_text, (
        f"{wf_name}: profile error must suggest fix command"
    )
    assert "exit 1" in wf_text, f"{wf_name}: preflight failures must exit non-zero"
    # Dedicated hermesbench-local label on self-hosted jobs
    assert "hermesbench-local" in wf_text, (
        f"{wf_name}: must target hermesbench-local label"
    )
    # flock-based lock on Hermes profile access
    assert "flock --exclusive" in wf_text, (
        f"{wf_name}: must use flock lock around Hermes profile access"
    )
    assert "/tmp/hermesbench-profile.lock" in wf_text, (
        f"{wf_name}: lock file path must be /tmp/hermesbench-profile.lock"
    )
    # Real-process smoke (not mock)
    assert "Acquire Hermes profile lock and run smoke" in wf_text, (
        f"{wf_name}: must have lock-acquired Hermes smoke step"
    )
    assert "mock" not in wf_text, f"{wf_name}: must not contain mock references"
    assert "self-hosted" in wf_text, f"{wf_name}: must target self-hosted runner"
    # Cloud-only jobs must NOT use self-hosted runner
    assert "ubuntu-latest" in wf_text, (
        f"{wf_name}: must have cloud-only jobs on ubuntu-latest"
    )


def _count_self_hosted_jobs(wf_text):
    """Count how many jobs reference the self-hosted runner label set."""
    import re
    return len(re.findall(r"runs-on:.*self-hosted", wf_text))


def test_release_has_real_hermes_smoke_and_no_mock_references():
    root = Path(__file__).resolve().parents[1]
    release = (root / ".github/workflows/release.yml").read_text()

    # Shared safety hardening
    _check_common_workflow_safety(release, "release.yml")

    # Release-specific assertions
    assert "uv run hermesbench run --agent hermes --profile hermesbench" in release
    assert "command -v hermes" in release
    assert "timeout-minutes: 30" in release
    # Hermes version pass-through in job outputs
    assert "hermes_version" in release
    # Cloud-only jobs in release must use ubuntu-latest
    assert "build-and-prepare" in release
    assert "package-and-publish" in release
    # Only 2 self-hosted jobs (real-agent-smoke, and... deploy not in release)
    assert _count_self_hosted_jobs(release) == 1, (
        "release.yml should only have 1 self-hosted job (real-agent-smoke)"
    )
    for path in [root / "README.md", root / "CHANGELOG.md", root / "REPOSITORY_MAP.md"]:
        text = path.read_text()
        assert "28 capability" not in text
        assert "official_runs/archive" not in text


def test_ci_workflow_has_safety_hardening():
    root = Path(__file__).resolve().parents[1]
    ci = _read_workflow(root, "ci.yml")
    _check_common_workflow_safety(ci, "ci.yml")
    assert "timeout-minutes: 30" in ci
    # Only 1 self-hosted job (real-agent-smoke)
    assert _count_self_hosted_jobs(ci) == 1, (
        "ci.yml should only have 1 self-hosted job (real-agent-smoke)"
    )


def test_vercel_prebuilt_workflow_has_safety_hardening():
    root = Path(__file__).resolve().parents[1]
    vp = _read_workflow(root, "vercel-prebuilt.yml")
    _check_common_workflow_safety(vp, "vercel-prebuilt.yml")
    assert "timeout-minutes: 15" in vp
    # Only real-agent-validate is self-hosted; deploy is cloud-only.
    assert _count_self_hosted_jobs(vp) == 1, (
        "vercel-prebuilt.yml should have 1 self-hosted job (real-agent-validate)"
    )


def test_website_build_archive_validation_python_equivalent(tmp_path):
    """The JS isOfficialArchiveSource in website/build.js must match the Python
    is_official_archive_source from scripts/archive_paths.py for the same inputs."""
    root = Path(__file__).resolve().parents[1]
    from scripts.archive_paths import is_official_archive_source as python_valid

    cases = [
        # valid
        ("official-runs/reviewed/hermesbench-reviewed.json", True),
        ("official-runs/run/result.json", True),
        ("official-runs/run/deep/path/result.json", True),
        ("official-runs/MyRun_1.0/result.json", True),
        # invalid
        ("official-runs/%2e%2e/result.json", False),
        ("official-runs/run/result.json?x=1", False),
        ("official-runs/run/result.json#fragment", False),
        ("official-runs\\\\run\\\\result.json", False),
        ("https://example.test/official-runs/run/result.json", False),
        ("official-runs//run/result.json", False),
        ("official-runs/./run/result.json", False),
        ("official-runs/../run/result.json", False),
        ("official-runs/run/../result.json", False),
        ("official-runs/run", False),
        ("official-runs/", False),
        ("results/run.json", False),
        ("/absolute/path/official-runs/run/result.json", False),
        ("official-runs/DASH-case/result.json", True),  # hyphens allowed
        ("official-runs/under_score/result.json", True),  # underscores allowed
        ("official-runs/dot.separated/result.json", True),  # dots allowed
        ("official-runs/run.1.2.3/result.json", True),
        ("official-runs/..run/result.json", False),  # starts with dot = traversal
        ("./official-runs/run/result.json", False),
        ("", False),
        (None, False),
    ]

    for source, expected in cases:
        assert python_valid(source) is expected, (
            f"Python: {source!r} should be {expected}"
        )

    # JS verification: evaluate isOfficialArchiveSource from build.js for each case
    website = tmp_path / "website"
    (website / "data").mkdir(parents=True)
    (website / "index.html").write_text("<main></main>")
    (website / "app.js").write_text("// test")
    (website / "index.css").write_text("/* test */")

    # Convert cases to JS-safe format (Python True/False -> JS true/false)
    js_cases = [(source, "true" if expected else "false") for source, expected in cases]
    js_cases_str = (
        "["
        + ",".join(
            f"[{json.dumps(source)},{val}]" if source is not None else f"[null,{val}]"
            for source, val in js_cases
        )
        + "]"
    )

    js_test = r"""const { isOfficialArchiveSource } = require(%s);
const cases = %s;
let failed = 0;
for (const [source, expected] of cases) {
  const actual = isOfficialArchiveSource(source);
  if (actual !== expected) {
    console.error(`FAIL: ${JSON.stringify(source)} => ${actual}, expected ${expected}`);
    failed++;
  }
}
if (failed) { process.exit(1); }
console.log(`JS/Python archive validation parity: ${cases.length} cases ok`);
""" % (json.dumps(str(root / "website/build.js")), js_cases_str)
    (website / "test-parity.js").write_text(js_test)

    result = subprocess.run(
        ["node", "test-parity.js"],
        cwd=website,
        text=True,
        capture_output=True,
    )
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)
    assert result.returncode == 0


def test_upload_payload_strips_logs_and_marks_unofficial(tmp_path):
    rp = _result(tmp_path / "hermesbench-r.json", "r", False)
    payload = make_submission_payload(rp)
    assert payload["classification"] == "unofficial"
    assert "logs" not in payload["result"]["results"][0]
    assert payload["github_issue"]["labels"] == ["hermesbench-submission", "unofficial"]


def test_discover_tasks_uses_task_root(tmp_path):
    root = tmp_path / "packs"
    suite = root / "fresh"
    suite.mkdir(parents=True)
    (root / "manifest.yaml").write_text(
        "suite: fresh\ntasks:\n- id: hb-private-001\n  path: fresh/task.md\n"
    )
    (suite / "task.md").write_text("""---
id: hb-private-001
title: Private
category: private
wave: fresh
visibility: private
created_at: '2026-06-01'
freshness_window: 30d
expected_human_minutes: 1
difficulty: easy
required_toolsets: []
grading_type: deterministic
timeout_seconds: 10
contamination_notes: none
safety_notes: none
---
## Prompt
Do it.
## Deterministic checks
- artifact_exists: out.txt
## Hidden checks
- maintained privately
""")
    tasks = discover_tasks("fresh", task_root=root)
    assert [t.metadata["id"] for t in tasks] == ["hb-private-001"]


def test_end_to_end_python_data_gen_to_js_build(tmp_path):
    """End-to-end regression: Python build_data -> generated JSON -> JS build.js.

    Creates real (minimal) result files, runs the full Python pipeline to
    produce leaderboard.json and per-run details, then invokes the actual
    website/build.js to validate, copy, and produce dist/. Asserts the build
    exits 0, generates all expected artifacts, and the JS validator reports
    successful validation of all JSON sources.
    """
    root = Path(__file__).resolve().parents[1]
    website = tmp_path / "website"
    results_dir = tmp_path / "results"
    out_dir = tmp_path / "out"
    manifest_tasks = discover_tasks("hermes-core")
    manifest_task_ids = {task.metadata["id"] for task in manifest_tasks}

    # ── Create result files using real manifest task records ───────────────
    def _make_result(subdir, run_id, suite, agent, official=False):
        path = results_dir / subdir / f"hermesbench-{run_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "schema_version": "hermesbench.result.v1",
            "run_id": run_id,
            "suite": suite,
            "agent": agent,
            "model": "fixture-model",
            "started_at": "2026-07-11T00:00:00Z",
            "completed_at": "2026-07-11T01:00:00Z",
            "metadata": {
                "official": official,
                "provider": "test-provider",
                "benchmark_version": "hermes-core-v0.1",
            },
            "results": [
                {
                    "task_id": task.metadata["id"],
                    "category": task.metadata["category"],
                    "status": "passed",
                    "score": 1.0,
                    "passed": True,
                    "wall_time_seconds": 1.0,
                    "tool_calls": 3,
                    "false_done": False,
                    "timeout": False,
                }
                for task in manifest_tasks
            ],
        }
        path.write_text(json.dumps(data))
        return path

    _make_result("official-reviewed", "o1", "hermes-core", "hermes", official=True)
    _make_result("unofficial-ci", "u1", "hermes-core", "test-agent", official=False)
    _make_result("unofficial-ci", "u2", "hermes-core", "test-agent", official=False)

    # ── Step 1: Run the Python data generator ─────────────────────────────
    lb = build_data(results_dir, out_dir)
    assert lb.exists(), "build_data must produce leaderboard.json"
    assert (out_dir / "runs/o1.json").exists(), "build_data must produce per-run detail"
    assert (out_dir / "runs/u1.json").exists(), "build_data must produce per-run detail"
    assert (out_dir / "runs/u2.json").exists(), "build_data must produce per-run detail"

    # Quick sanity on the leaderboard content (contract-level, not brittle)
    lb_data = json.loads(lb.read_text())
    assert lb_data["schema_version"] == "hermesbench.website.leaderboard.v3"
    assert len(lb_data["official"]) >= 1
    assert len(lb_data["unofficial"]) >= 1
    assert len(lb_data["entries"]) == 3
    generated_run = json.loads((out_dir / "runs/o1.json").read_text())
    assert {task["task_id"] for task in generated_run["tasks"]} == manifest_task_ids

    # ── Step 2: Set up website fixture directory ──────────────────────────
    (website / "data").mkdir(parents=True)
    (website / "index.html").write_text("<html><body></body></html>")
    (website / "app.js").write_text("// test app stub")
    (website / "index.css").write_text("/* test */")

    # Copy generated data files into the website fixture
    import shutil
    shutil.copy(out_dir / "leaderboard.json", website / "data/leaderboard.json")
    for detail_file in (out_dir / "runs").iterdir():
        shutil.copy(detail_file, website / f"data/{detail_file.name}")

    # ── Step 3: Run the real JS build ─────────────────────────────────────
    build_script = root / "website/build.js"
    result = subprocess.run(
        ["node", str(build_script)],
        cwd=website,
        text=True,
        capture_output=True,
    )

    # Print build output for debugging test failures
    print(result.stdout)
    if result.returncode != 0:
        print(result.stderr)

    # ── Step 4: Assertions ────────────────────────────────────────────────
    assert result.returncode == 0, (
        f"JS build failed with rc={result.returncode}\n"
        f"STDERR:\n{result.stderr}"
    )

    # Build outputs
    dist = website / "dist"
    assert dist.is_dir(), "build.js must create dist/ directory"
    assert (dist / "index.html").is_file(), "dist/index.html must exist"
    assert (dist / "app.js").is_file(), "dist/app.js must exist"
    assert (dist / "data/leaderboard.json").is_file(), "dist/data/leaderboard.json must exist"
    assert (dist / "data/o1.json").is_file(), "dist/data/o1.json (run detail) must exist"
    assert (dist / "data/u1.json").is_file(), "dist/data/u1.json (run detail) must exist"
    assert (dist / "data/u2.json").is_file(), "dist/data/u2.json (run detail) must exist"

    # The build validates every JSON it reads — confirm validation logged
    assert "all public JSON provenance and paths validated" in result.stdout, (
        "JS build must output successful validation marker"
    )

    # Confirm the dist copy is valid JSON and matches schema version
    dist_lb = json.loads((dist / "data/leaderboard.json").read_text())
    assert dist_lb["schema_version"] == "hermesbench.website.leaderboard.v3"
    assert len(dist_lb["entries"]) == 3
    dist_run = json.loads((dist / "data/o1.json").read_text())
    assert {task["task_id"] for task in dist_run["tasks"]} == manifest_task_ids


# ── Parameterized parse_task_markdown coverage ──────────────────────────────


class TestParseTaskMarkdown:
    """``parse_task_markdown`` must handle every deterministic check type,
    missing/empty sections, YAML edge cases, and the five ``grading_type``
    values the schema allows.

    These are white-box tests exercising the parser directly on synthetic
    markdown — they don't require a real task tree.
    """

    # ── Helpers ──────────────────────────────────────────────────────────

    MINIMAL_FRONTMATTER = """\
---
id: test
title: Test
category: natural-tool-use
wave: 1
visibility: public
created_at: 2026-01-01
freshness_window: static
expected_human_minutes: 1
difficulty: easy
required_toolsets: [terminal]
grading_type: deterministic
timeout_seconds: 30
contamination_notes: none
safety_notes: none
---
"""

    @staticmethod
    def _markdown(body: str, frontmatter: str | None = None) -> str:
        """Wrap *body* in minimal-YAML frontmatter so the parser reaches the sections."""
        return (frontmatter or TestParseTaskMarkdown.MINIMAL_FRONTMATTER) + body

    # ── Check-type coverage ─────────────────────────────────────────────

    def test_artifact_exists(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- artifact_exists: done.txt\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "artifact_exists", "path": "done.txt"}]

    def test_artifact_contains(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- artifact_contains: out.txt => expected\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "artifact_contains", "path": "out.txt", "needle": "expected"}]

    def test_json_field(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- json_field: report.json => ok=true\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "json_field", "path": "report.json", "expr": "ok=true"}]

    def test_command_passes(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- command_passes: test -f done.txt\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "command_passes", "command": "test -f done.txt"}]

    def test_artifact_not_contains(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- artifact_not_contains: out.txt => error\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "artifact_not_contains", "path": "out.txt", "needle": "error"}]

    def test_artifact_matches(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- artifact_matches: answer.txt => \\d+\\.\\d+\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "artifact_matches", "path": "answer.txt", "pattern": "\\d+\\.\\d+"}]

    def test_artifact_not_matches(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- artifact_not_matches: answer.txt => error.*\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "artifact_not_matches", "path": "answer.txt", "pattern": "error.*"}]

    def test_glob_exists(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- glob_exists: *.log\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "glob_exists", "pattern": "*.log"}]

    def test_command_contains(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- command_contains: cat answer.txt => 42\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "command_contains", "command": "cat answer.txt", "needle": "42"}]

    def test_command_not_contains(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Deterministic checks\n- command_not_contains: cat answer.txt => unknown\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == [{"type": "command_not_contains", "command": "cat answer.txt", "needle": "unknown"}]

    # ── Multiple checks ─────────────────────────────────────────────────

    def test_multiple_checks(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown(
            "## Deterministic checks\n"
            "- artifact_exists: a.txt\n"
            "- artifact_contains: b.txt => ok\n"
            "- command_passes: test -f c.txt\n"
        ))
        t = parse_task_markdown(md)
        assert len(t.deterministic_checks) == 3
        assert t.deterministic_checks[0] == {"type": "artifact_exists", "path": "a.txt"}
        assert t.deterministic_checks[1] == {"type": "artifact_contains", "path": "b.txt", "needle": "ok"}
        assert t.deterministic_checks[2] == {"type": "command_passes", "command": "test -f c.txt"}

    # ── Section extraction ──────────────────────────────────────────────

    def test_prompt_scoring_and_expected_artifacts(self, tmp_path):
        body = (
            "## Prompt\nDo the thing.\n"
            "## Expected artifacts\n- out.txt\n"
            "## Scoring rubric\nMust pass.\n"
            "## Deterministic checks\n- artifact_exists: out.txt\n"
        )
        md = tmp_path / "t.md"
        md.write_text(self._markdown(body))
        t = parse_task_markdown(md)
        assert t.prompt == "Do the thing."
        assert t.expected_artifacts == ["out.txt"]
        assert t.scoring_rubric == "Must pass."

    def test_setup_and_cleanup(self, tmp_path):
        body = (
            "## Setup\nCopy fixture.\n"
            "## Prompt\nDo it.\n"
            "## Deterministic checks\n- artifact_exists: done.txt\n"
            "## Cleanup\nDelete workdir.\n"
        )
        md = tmp_path / "t.md"
        md.write_text(self._markdown(body))
        t = parse_task_markdown(md)
        assert t.setup == "Copy fixture."
        assert t.cleanup == "Delete workdir."

    def test_hidden_checks(self, tmp_path):
        body = (
            "## Prompt\nDo it.\n"
            "## Deterministic checks\n- artifact_exists: out.txt\n"
            "## Hidden checks\n- redacted: true\n"
        )
        md = tmp_path / "t.md"
        md.write_text(self._markdown(body))
        t = parse_task_markdown(md)
        assert t.hidden_checks == ["redacted: true"]

    # ── Edge cases ──────────────────────────────────────────────────────

    def test_missing_frontmatter_raises(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text("## Prompt\nNo frontmatter.\n")
        with pytest.raises(ValueError, match="missing YAML frontmatter"):
            parse_task_markdown(md)

    def test_empty_frontmatter_is_empty_dict(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text("---\n---\n## Prompt\nBody.\n")
        with pytest.raises(ValueError, match="missing metadata"):
            parse_task_markdown(md)

    def test_no_deterministic_checks_is_empty_list(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Prompt\nDo it.\n"))
        t = parse_task_markdown(md)
        assert t.deterministic_checks == []

    def test_absent_sections_return_empty(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(self._markdown("## Prompt\nDo it.\n## Deterministic checks\n- artifact_exists: done.txt\n"))
        t = parse_task_markdown(md)
        assert t.setup == ""
        assert t.scoring_rubric == ""
        assert t.cleanup == ""

    def test_empty_line_between_sections(self, tmp_path):
        md = tmp_path / "t.md"
        md.write_text(
            self._markdown(
                "## Prompt\nDo it.\n\n## Deterministic checks\n- artifact_exists: done.txt\n\n"
                "## Hidden checks\n- none\n"
            )
        )
        t = parse_task_markdown(md)
        assert t.prompt == "Do it."
        assert not t.deterministic_checks[0].get("needle")

    def test_required_toolsets_as_list(self, tmp_path):
        """Verify that YAML list-typed required_toolsets parse correctly."""
        fm = """\
---
id: test
title: Test
category: natural-tool-use
wave: 1
visibility: public
created_at: 2026-01-01
freshness_window: static
expected_human_minutes: 1
difficulty: easy
required_toolsets:
- terminal
- file
grading_type: deterministic
timeout_seconds: 30
contamination_notes: none
safety_notes: none
---
"""
        md = tmp_path / "t.md"
        md.write_text(fm + "## Prompt\nDo.\n## Deterministic checks\n- artifact_exists: done.txt\n")
        t = parse_task_markdown(md)
        assert t.metadata["required_toolsets"] == ["terminal", "file"]

    def test_all_five_grading_types_accepted(self, tmp_path):
        """The schema allows exactly {'deterministic','artifact','test','judge','hybrid'}."""
        for gt in ("deterministic", "artifact", "test", "judge", "hybrid"):
            fm = self.MINIMAL_FRONTMATTER.replace("grading_type: deterministic", f"grading_type: {gt}")
            md = tmp_path / f"t-{gt}.md"
            md.write_text(fm + "## Prompt\nDo.\n## Deterministic checks\n- artifact_exists: done.txt\n")
            t = parse_task_markdown(md)
            assert t.metadata["grading_type"] == gt

    def test_invalid_grading_type_raises(self, tmp_path):
        fm = self.MINIMAL_FRONTMATTER.replace("grading_type: deterministic", "grading_type: invalid")
        md = tmp_path / "t.md"
        md.write_text(fm + "## Prompt\nDo.\n")
        with pytest.raises(ValueError, match="bad grading_type"):
            parse_task_markdown(md)
