"""Synchronize published suite counts from tasks/manifest.yaml.

The manifest is the source of truth. This script updates the small static
surfaces that cannot import the Python task inventory (the website and README).
"""
from __future__ import annotations

import argparse
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "tasks" / "manifest.yaml"


def counts() -> tuple[int, int]:
    data = yaml.safe_load(MANIFEST.read_text())
    suites = data["suites"]
    core = len(suites["hermes-core"]["tasks"])
    extended = len(suites["hermes-extended"]["tasks"])
    return core, extended


def replace_once(path: Path, pattern: str, replacement: str, *, check: bool) -> None:
    text = path.read_text()
    updated, changed = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if changed != 1:
        raise SystemExit(f"{path}: expected exactly one count block, found {changed}")
    if check:
        if updated != text:
            raise SystemExit(f"{path}: suite counts are stale; run scripts/sync_suite_counts.py")
    else:
        path.write_text(updated)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if generated surfaces are stale")
    args = parser.parse_args()
    core, extended = counts()
    total = core + extended
    app = ROOT / "website" / "app.js"
    replace_once(
        app,
        r"const taskStats = \{[\s\S]*?\n  categories:",
        "const taskStats = {\n"
        f"  total: {total},\n"
        f"  hermesCore: {core},\n"
        f"  hermesExtended: {extended},\n"
        "  packs: [\n"
        f"    ['Hermes Core', 'hermes-core', '{core}', 'Tools and features shipped in the base Hermes Agent installation.'],\n"
        f"    ['Hermes Extended', 'hermes-extended', '{extended}', 'Installable/configurable tools and integrations; unavailable tools are environment skips.'],\n"
        "  ],\n"
        "  categories:",
        check=args.check,
    )
    readme = ROOT / "README.md"
    replace_once(
        readme,
        r"\| `hermes-core` \| \d+ \|([^\n]+)\n\| `hermes-extended` \| \d+ \|",
        f"| `hermes-core` | {core} |\\1\n| `hermes-extended` | {extended} |",
        check=args.check,
    )
    print(f"synced suite counts: hermes-core={core}, hermes-extended={extended}, total={total}")


if __name__ == "__main__":
    main()
