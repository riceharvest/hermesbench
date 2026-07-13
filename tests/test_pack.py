from pathlib import Path

import pytest

from hermesbench.pack import canonical_pack_sha256


def _pack(root: Path) -> None:
    root.mkdir()
    (root / "manifest.yaml").write_text("suite: private\n")
    (root / "tasks").mkdir()
    (root / "tasks" / "a.md").write_text("task\n")


def test_pack_hash_is_stable_and_detects_mutation(tmp_path):
    root = tmp_path / "pack"
    _pack(root)
    first = canonical_pack_sha256(root)
    assert len(first) == 64
    assert canonical_pack_sha256(root) == first
    (root / "tasks" / "a.md").write_text("changed\n")
    assert canonical_pack_sha256(root) != first


def test_pack_hash_ignores_transient_outputs(tmp_path):
    root = tmp_path / "pack"
    _pack(root)
    first = canonical_pack_sha256(root)
    (root / "outputs").mkdir()
    (root / "outputs" / "run.json").write_text("secret output")
    assert canonical_pack_sha256(root) == first


def test_pack_hash_requires_manifest(tmp_path):
    with pytest.raises(ValueError, match="manifest"):
        canonical_pack_sha256(tmp_path)
