from __future__ import annotations

import hashlib
from pathlib import Path

_IGNORED_NAMES = {".DS_Store"}
_IGNORED_PARTS = {"__pycache__", ".pytest_cache", ".git", "runs", "outputs"}


def canonical_pack_sha256(root: str | Path) -> str:
    """Hash all stable pack bytes using sorted POSIX relative paths.

    Filesystem metadata and transient cache/output directories are excluded.
    File bytes are hashed exactly; pack authors must normalize text before freeze.
    """
    root = Path(root).resolve()
    if not (root / "manifest.yaml").is_file():
        raise ValueError("private task pack must contain manifest.yaml")
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.name not in _IGNORED_NAMES
        and not any(part in _IGNORED_PARTS for part in path.relative_to(root).parts)
    ]
    digest = hashlib.sha256()
    for path in sorted(files, key=lambda item: item.relative_to(root).as_posix()):
        relative = path.relative_to(root).as_posix().encode("utf-8")
        data = path.read_bytes()
        digest.update(len(relative).to_bytes(8, "big"))
        digest.update(relative)
        digest.update(len(data).to_bytes(8, "big"))
        digest.update(data)
    return digest.hexdigest()
