#!/usr/bin/env python3
"""Create starter files for a HermesBench fresh rolling wave."""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def create_wave(wave: str, count: int, root: Path = ROOT) -> list[Path]:
    if not wave.startswith("fresh-"):
        raise SystemExit("wave must start with fresh-")
    if count < 1:
        raise SystemExit("count must be positive")
    wave_dir = root / "tasks" / "fresh-rolling" / wave
    fixture_root = root / "fixtures" / wave
    wave_dir.mkdir(parents=True, exist_ok=True)
    fixture_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    manifest = wave_dir / "manifest.yaml"
    if not manifest.exists():
        manifest.write_text(f"wave: {wave}\nstatus: draft\nminimum_task_count: {count}\ntasks:\n")
        written.append(manifest)
    for i in range(1, count + 1):
        task_id = f"{wave}-{i:03d}"
        task_file = wave_dir / f"{task_id}.md"
        fixture_dir = fixture_root / task_id
        fixture_dir.mkdir(parents=True, exist_ok=True)
        readme = fixture_dir / "README.md"
        if not readme.exists():
            readme.write_text(f"# Fixtures for {task_id}\n\nTODO: replace with redistributable fresh-wave fixtures.\n")
            written.append(readme)
        if not task_file.exists():
            task_file.write_text(
                f"""---
id: {task_id}
suite: fresh-rolling
wave: {wave}
visibility: public
status: draft
category: TODO
freshness_window_start: TODO
freshness_window_end: TODO
expected_artifacts:
  - artifacts/{task_id}-report.md
deterministic_checks:
  - type: artifact_exists
    path: artifacts/{task_id}-report.md
contamination_notes: TODO - document source freshness and leakage review before validation.
---

# {task_id}

TODO: Write a fresh-wave task prompt. This stub is intentionally incomplete and should fail quality review until filled in.

## Expected artifacts
- `artifacts/{task_id}-report.md`

## Scoring rubric
TODO: Add deterministic/test scoring details.
"""
            )
            written.append(task_file)
        text = manifest.read_text()
        if f"  - {task_id}\n" not in text:
            with manifest.open("a") as fh:
                fh.write(f"  - {task_id}\n")
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave", required=True)
    parser.add_argument("--count", required=True, type=int)
    args = parser.parse_args()
    written = create_wave(args.wave, args.count)
    print(f"created {args.wave} starter wave; wrote {len(written)} files")


if __name__ == "__main__":
    main()
