#!/usr/bin/env python3
"""Inspect or install an external HermesBench private task pack.

Private packs live outside the public repository and are selected at runtime with
HERMESBENCH_PRIVATE_PACK_DIR. A pack must contain a manifest.yaml plus task files
using the normal HermesBench task layout. This helper validates that layout and can
copy a pack into an operator-controlled destination; it never creates or commits
secrets into this repo.
"""
from __future__ import annotations

import argparse
import os
import shutil
from pathlib import Path


def pack_dir_from_env() -> Path:
    value = os.environ.get("HERMESBENCH_PRIVATE_PACK_DIR")
    if not value:
        raise SystemExit("set HERMESBENCH_PRIVATE_PACK_DIR to an external private pack directory")
    return Path(value).expanduser().resolve()


def validate_pack(path: Path) -> list[str]:
    errors: list[str] = []
    manifest = path / "manifest.yaml"
    if not manifest.exists():
        errors.append(f"missing {manifest}")
    if not any(path.glob("*/*.md")):
        errors.append(f"no task markdown files under {path}/*/*.md")
    fixture_root = path.parent / "fixtures"
    if not fixture_root.exists() and not (path / "fixtures").exists():
        errors.append("no sibling or in-pack fixtures directory found")
    return errors


def install_pack(src: Path, dest: Path) -> None:
    if dest.exists():
        raise SystemExit(f"destination already exists: {dest}")
    shutil.copytree(src, dest)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack", type=Path, default=None, help="external pack directory; defaults to HERMESBENCH_PRIVATE_PACK_DIR")
    parser.add_argument("--install-to", type=Path, default=None, help="optional operator-controlled copy destination")
    args = parser.parse_args()
    pack = (args.pack.expanduser().resolve() if args.pack else pack_dir_from_env())
    errors = validate_pack(pack)
    if errors:
        raise SystemExit("invalid private pack:\n- " + "\n- ".join(errors))
    if args.install_to:
        install_pack(pack, args.install_to.expanduser().resolve())
        print(f"installed private pack to {args.install_to}")
    else:
        print(f"private pack OK: {pack}")
        print(f"Use: HERMESBENCH_PRIVATE_PACK_DIR={pack} hermesbench validate-tasks")


if __name__ == "__main__":
    main()
