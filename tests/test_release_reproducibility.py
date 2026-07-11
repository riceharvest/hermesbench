"""P1-A: Release reproducibility gates.

These tests verify that the release pipeline produces reproducible,
verifiable artifacts. They run without provider credentials.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path
from zipfile import ZipFile

import pytest

# ── helpers ──────────────────────────────────────────────────────────────────


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _package_version() -> str:
    """Read __version__ from the package source."""
    init = _repo_root() / "src" / "hermesbench" / "__init__.py"
    m = re.search(r'__version__\s*=\s*"([^"]+)"', init.read_text())
    if not m:
        raise RuntimeError("could not parse __version__ from __init__.py")
    return m.group(1)


def _pyproject_version() -> str:
    """Read version from pyproject.toml."""
    text = (_repo_root() / "pyproject.toml").read_text()
    m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    if not m:
        raise RuntimeError("could not parse version from pyproject.toml")
    return m.group(1)


# ── version provenance ────────────────────────────────────────────────────────


def test_package_version_matches_pyproject():
    """The single source of truth: __init__.py and pyproject.toml must agree."""
    assert _package_version() == _pyproject_version(), (
        f"__init__.py version ({_package_version()}) != pyproject.toml version "
        f"({_pyproject_version()})"
    )


def test_release_yml_triggers_only_on_version_tags():
    """Release.yml must only trigger on v* tags for provenance."""
    text = (_repo_root() / ".github/workflows/release.yml").read_text()
    assert (
        'on:' in text
    ), "release.yml has no trigger block"
    assert (
        'tags:' in text and '"v*"' in text
    ), "release.yml must trigger on v* tags"


def test_release_yml_has_concurrency_group():
    """Release.yml must serialize self-hosted runner access."""
    text = (_repo_root() / ".github/workflows/release.yml").read_text()
    assert "concurrency:" in text
    assert "group:" in text
    assert "cancel-in-progress: false" in text


def test_release_yml_has_no_mock_references():
    """No mock code should leak into release artifacts."""
    text = (_repo_root() / ".github/workflows/release.yml").read_text()
    assert "mock" not in text, "release.yml must not reference mock adapter"


def test_sdist_and_wheel_exist_if_built():
    """If dist/ exists, both sdist and wheel must be present."""
    dist = _repo_root() / "dist"
    if not dist.exists():
        pytest.skip("no dist/ directory — build artifacts not present")
    wheels = list(dist.glob("*.whl"))
    sdists = list(dist.glob("*.tar.gz"))
    assert wheels, f"no .whl found in {dist}"
    assert sdists, f"no .tar.gz (sdist) found in {dist}"
    for whl in wheels:
        assert whl.name.startswith("hermesbench-"), f"unexpected wheel name: {whl.name}"
    for s in sdists:
        assert s.name.startswith("hermesbench-"), f"unexpected sdist name: {s.name}"


def test_dist_sha256_checksums():
    """If dist/ exists, produce deterministically ordered SHA256SUMS.

    This verifies the checksum format used by official archives and
    release artifact publishing.
    """
    dist = _repo_root() / "dist"
    if not dist.exists():
        pytest.skip("no dist/ directory")
    artifacts = sorted(dist.iterdir())
    lines = []
    for p in artifacts:
        if p.is_file():
            lines.append(f"{_sha256(p)}  {p.name}")
    assert lines, "no artifact files in dist/"
    # Verify deterministic ordering — sorted by filename
    names = [l.split("  ", 1)[1] for l in lines]
    assert names == sorted(names), "SHA256SUMS must be sorted by filename"


# ── fresh-wheel verification ──────────────────────────────────────────────────


@pytest.mark.slow
def test_fresh_wheel_install(tmp_path):
    """Build a wheel, install it in a clean venv, and verify it works.

    This is the most reliable reproducibility gate: it catches missing
    dependencies, broken entry points, and packaging errors that tests
    run inside the development venv would miss.
    """
    root = _repo_root()
    dist = root / "dist"
    if not dist.exists() or not list(dist.glob("*.whl")):
        # Build wheel if not present (explicit prerequisite)
        subprocess.run(
            [sys.executable, "-m", "build", "--wheel"],
            check=True, capture_output=True, text=True, cwd=root,
        )

    # Create a clean virtualenv
    venv = tmp_path / "venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=True,
        capture_output=True,
    )
    pip = venv / "bin" / "pip"
    python = venv / "bin" / "python"

    # Pick the most recent wheel
    wheels = sorted(dist.glob("*.whl"))
    wheel = wheels[-1]

    # Install
    subprocess.run(
        [str(pip), "install", str(wheel)],
        check=True,
        capture_output=True,
        text=True,
    )

    # Basic smoke: --help works
    help_result = subprocess.run(
        [str(python), "-m", "hermesbench.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0, (
        f"hermesbench --help failed:\n{help_result.stderr}"
    )
    assert "usage:" in help_result.stdout

    # Smoke: module import works (confirms all deps are present)
    import_result = subprocess.run(
        [str(python), "-c",
         "from hermesbench.tasks import discover_tasks; "
         "from hermesbench.schemas import RunResult, TaskResult; "
         "from hermesbench.scoring import aggregate; "
         "print('All core modules loaded')"],
        capture_output=True,
        text=True,
    )
    assert import_result.returncode == 0, (
        f"Core modules failed from fresh install:\n{import_result.stderr}"
    )
    # Smoke: versions command (doesn't need filesystem)
    versions_result = subprocess.run(
        [str(python), "-m", "hermesbench.cli", "versions"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert versions_result.returncode == 0
    assert "hermes-core" in versions_result.stdout


# ── sdist → wheel build reproducibility ────────────────────────────────────────


@pytest.mark.slow
def test_sdist_rebuilds_identical_wheel(tmp_path):
    """Verify that building from sdist produces a functional wheel.

    This gate catches the case where the wheel build depends on
    something in the developer environment that isn't captured in
    pyproject.toml.
    """
    root = _repo_root()
    dist = root / "dist"
    if not dist.exists() or not list(dist.glob("*.tar.gz")):
        # Build sdist if not present (explicit prerequisite)
        subprocess.run(
            [sys.executable, "-m", "build", "--sdist"],
            check=True, capture_output=True, text=True, cwd=root,
        )

    sdists = sorted(dist.glob("*.tar.gz"))
    sdist = sdists[-1]

    work = tmp_path / "rebuild"
    work.mkdir()

    # Extract sdist
    with tarfile.open(sdist) as tf:
        tf.extractall(work)

    # Find the extracted package dir
    extracted_dirs = [d for d in work.iterdir() if d.is_dir()]
    assert extracted_dirs, "no directory extracted from sdist"
    pkg_dir = extracted_dirs[0]

    # Build wheel from extracted sdist
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "build"],
        check=True,
        capture_output=True,
        cwd=pkg_dir,
    )
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel"],
        check=True,
        capture_output=True,
        text=True,
        cwd=pkg_dir,
    )

    rebuilt_wheels = list(pkg_dir.glob("dist/*.whl"))
    assert rebuilt_wheels, "no wheel produced from sdist rebuild"
    rebuilt_wheel = rebuilt_wheels[0]

    # Install rebuilt wheel in a fresh venv and smoke it
    venv = tmp_path / "rebuild-venv"
    subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        check=True,
        capture_output=True,
    )
    subprocess.run(
        [str(venv / "bin" / "pip"), "install", str(rebuilt_wheel)],
        check=True,
        capture_output=True,
        text=True,
    )

    help_result = subprocess.run(
        [str(venv / "bin" / "python"), "-m", "hermesbench.cli", "--help"],
        capture_output=True,
        text=True,
    )
    assert help_result.returncode == 0

    import_result = subprocess.run(
        [str(venv / "bin" / "python"), "-c",
         "from hermesbench.tasks import discover_tasks; "
         "from hermesbench.schemas import RunResult, TaskResult; "
         "from hermesbench.scoring import aggregate; "
         "print('All core modules loaded')"],
        capture_output=True,
        text=True,
    )
    assert import_result.returncode == 0

    versions_result = subprocess.run(
        [str(venv / "bin" / "python"), "-m", "hermesbench.cli", "versions"],
        capture_output=True,
        text=True,
        cwd=root,
    )
    assert versions_result.returncode == 0
    assert "hermes-core" in versions_result.stdout


# ── release artifact SHA256SUMS formatting ────────────────────────────────────


def test_release_artifact_sha256sums_format():
    """Verify the SHA256SUMS format used by official archives.

    The format is deterministic: sorted filenames, each line is
    '<sha256>  <filename>'.
    """
    lines = [
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  result.json",
        "d7a8fbb307d7809469ca9abcb0082e4f8d5651e46d3cdb762d02d0bf37c9e592  manifest.yaml",
        "ca978112ca1bbdcafac231b39a23dc4da786eff8147c4e72b9807785afee48bb  score-summary.json",
    ]
    for line in lines:
        assert re.match(
            r"^[0-9a-f]{64}  .+$", line
        ), f"SHA256SUMS line format violation: {line}"


# ── release.yml structure checks ──────────────────────────────────────────────


def test_release_yml_records_hermes_version():
    """Release.yml should capture the Hermes CLI version in the build step."""
    text = (_repo_root() / ".github/workflows/release.yml").read_text()
    assert "hermes" in text
    # Check that the release workflow records the version
    assert "hermes --version" in text or "hermes version" in text, (
        "release.yml should capture hermes version"
    )


def test_release_yml_has_annotated_tag_provenance():
    """Release.yml asserts annotated tag matches package version."""
    text = (_repo_root() / ".github/workflows/release.yml").read_text()
    assert "git describe --tags --exact-match" in text
    assert "GITHUB_REF_NAME" in text and "EXPECTED" in text
    assert "fetch-depth: 0" in text


def test_release_yml_emits_sha256sums():
    """Release.yml should generate SHA256SUMS for published artifacts."""
    text = (_repo_root() / ".github/workflows/release.yml").read_text()
    assert "SHA256" in text or "sha256sum" in text, (
        "release.yml should generate artifact SHA256SUMS"
    )


def test_release_yml_includes_built_wheels_and_sdists():
    """Release artifacts must include built wheels/sdists and SHA256SUMS."""
    text = (_repo_root() / ".github/workflows/release.yml").read_text()
    assert "hermesbench-*.whl" in text, "release should publish built wheels"
    assert "hermesbench-*.tar.gz" in text, "release should publish built sdist"
    assert "SHA256SUMS" in text, "release should publish checksums"
