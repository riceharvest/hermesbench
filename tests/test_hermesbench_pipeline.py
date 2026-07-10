from __future__ import annotations
import json
from pathlib import Path
import subprocess

from scripts.generate_website_data import build_data, is_official_archive_source
from hermesbench.submissions import make_submission_payload
from hermesbench.tasks import discover_tasks


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
    _result(tmp_path / "external-results/u/hermesbench-u.json", "u", False)

    lb = build_data(tmp_path / "external-results", tmp_path / "out")
    data = json.loads(lb.read_text())
    assert "source" not in data["entries"][0]


def test_website_generator_only_marks_reviewed_official_archives_as_capability_evidence(
    tmp_path, monkeypatch
):
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

    result = subprocess.run(
        ["node", str(root / "website/build.js")],
        cwd=website,
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0


def test_app_has_honest_no_results_state():
    app = (Path(__file__).resolve().parents[1] / "website/app.js").read_text()

    assert "No reviewed results are published yet" in app
    assert "function isCapabilityData" in app
    assert "function isCapabilityRun" in app


def test_app_has_no_static_mock_fallback():
    app = (Path(__file__).resolve().parents[1] / "website/app.js").read_text()

    assert "historical_mock" not in app
    assert "static fallback" not in app.lower()
    assert "data/leaderboard.json" not in app


def test_visible_suite_counts_match_the_manifest_contract():
    root = Path(__file__).resolve().parents[1]
    app = (root / "website/app.js").read_text()
    readme = (root / "README.md").read_text()

    assert "total: 38" in app
    assert "coreCli: 3" in app
    assert "integrations: 35" in app
    assert "| `core-cli` | 3 |" in readme
    assert "| `integrations` | 35 |" in readme


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
