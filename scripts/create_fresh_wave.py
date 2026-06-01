#!/usr/bin/env python3
"""Generate a redistributable HermesBench fresh rolling wave.

The generator writes non-placeholder task specs plus deterministic local fixtures with
rotated dataset ids, dates, policy codes, checksums, and record values.
"""
from __future__ import annotations

import argparse
import hashlib
import random
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATEGORIES = [
    ("research-freshness", "research-brief"),
    ("codebase-navigation", "code-map"),
    ("csv-data-analysis", "csv-summary"),
    ("provider-config-troubleshooting", "provider-fix"),
    ("false-done-verification", "verification-audit"),
]


def _case_values(wave: str, index: int, category: str, seed: str | None = None) -> dict[str, object]:
    rng = random.Random(f"{wave}:{index}:{category}:{seed or ''}")
    records = [rng.randrange(17, 113) for _ in range(5 + rng.randrange(4))]
    dataset_id = f"{wave.upper().replace('-', '')}-{index:03d}-{rng.randrange(1000,9999)}"
    checksum = hashlib.sha256((dataset_id + ":" + ",".join(map(str, records))).encode()).hexdigest()[:16]
    start = date.fromisoformat(wave.removeprefix("fresh-") + "-01") if len(wave) == 13 else date.today()
    return {
        "dataset_id": dataset_id,
        "policy_code": f"HB-FRESH-{rng.randrange(100,999)}",
        "owner": rng.choice(["Ari", "Bo", "Cy", "Dee", "Eli"]),
        "deadline": (start + timedelta(days=7 + index)).isoformat(),
        "records": records,
        "expected_total": sum(records),
        "record_count": len(records),
        "checksum": checksum,
    }


def create_wave(wave: str, count: int, root: Path = ROOT, seed: str | None = None) -> list[Path]:
    if not wave.startswith("fresh-"):
        raise SystemExit("wave must start with fresh-")
    if count < 1:
        raise SystemExit("count must be positive")
    wave_dir = root / "tasks" / "fresh-rolling" / wave
    fixture_root = root / "fixtures" / wave
    wave_dir.mkdir(parents=True, exist_ok=True)
    fixture_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    manifest_lines = [f"wave: {wave}", "status: ready", f"minimum_task_count: {count}", "tasks:"]
    for i in range(1, count + 1):
        category, kind = CATEGORIES[(i - 1) % len(CATEGORIES)]
        task_id = f"{wave}-{i:03d}-{category}"
        values = _case_values(wave, i, category, seed)
        artifact = f"artifacts/{task_id}-report.json"
        fixture_dir = fixture_root / task_id
        fixture_dir.mkdir(parents=True, exist_ok=True)
        case = fixture_dir / "case-file.txt"
        records = list(values["records"])  # type: ignore[arg-type]
        case.write_text(
            f"fixture_version: {wave}\nfixture_kind: {kind}\ndataset_id: {values['dataset_id']}\n"
            f"policy_code: {values['policy_code']}\nowner: {values['owner']}\ndeadline: {values['deadline']}\n"
            f"records: {','.join(map(str, records))}\nexpected_total: {values['expected_total']}\n"
            f"record_count: {values['record_count']}\nchecksum: {values['checksum']}\n"
        )
        written.append(case)
        task_file = wave_dir / f"{task_id}.md"
        task_file.write_text(f"""---
id: {task_id}
title: "Fresh rolling {i}: {category}"
category: {category}
wave: {wave}
visibility: public
created_at: {date.today().isoformat()}
freshness_window: rolling-30d
expected_human_minutes: 10
difficulty: medium
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 240
contamination_notes: "Generated fresh task with rotated fixture values for {wave}."
safety_notes: "Local fixture only; no credentials or external side effects."
---

## Prompt
Inspect `case-file.txt` in the seeded fixture for `{task_id}` and write `{artifact}` as valid JSON containing `task_id`, `dataset_id`, `policy_code`, `owner`, `deadline`, `record_count`, `expected_total`, `checksum`, `category_finding`, and `verified: true`. Recompute `expected_total` from the records before writing the artifact.

## Expected artifacts
- `{artifact}`

## Scoring rubric
Pass requires exact fixture extraction plus semantic arithmetic verification; marker-only completion fails.

## Deterministic checks
- artifact_exists: {artifact}
- artifact_json_field_equals: {artifact} => task_id == {task_id}
- artifact_json_field_equals: {artifact} => dataset_id == {values['dataset_id']}
- artifact_json_field_equals: {artifact} => policy_code == {values['policy_code']}
- artifact_json_field_equals: {artifact} => record_count == {values['record_count']}
- artifact_json_field_equals: {artifact} => expected_total == {values['expected_total']}
- artifact_json_field_equals: {artifact} => checksum == {values['checksum']}
- semantic_check: recompute sum(records) from fixture and compare to `expected_total`
""")
        written.append(task_file)
        manifest_lines.append(f"  - id: {task_id}\n    path: {task_file.relative_to(root / 'tasks')}\n    category: {category}\n    fixture: {fixture_dir.relative_to(root)}")
    manifest = wave_dir / "manifest.yaml"
    manifest.write_text("\n".join(manifest_lines) + "\n")
    written.append(manifest)
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--wave", required=True)
    parser.add_argument("--count", required=True, type=int)
    parser.add_argument("--seed", default=None, help="optional rotation seed for reproducible official generation")
    args = parser.parse_args()
    written = create_wave(args.wave, args.count, seed=args.seed)
    print(f"created {args.wave} fresh wave; wrote {len(written)} files")


if __name__ == "__main__":
    main()
