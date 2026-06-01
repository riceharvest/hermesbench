---
id: hb-fre-004-provider-config-troubleshooting
title: "Fresh Rolling 004: provider-config-troubleshooting"
category: provider-config-troubleshooting
wave: fresh
visibility: public
created_at: 2026-06-02
freshness_window: rolling-30d
expected_human_minutes: 13
difficulty: medium
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 240
contamination_notes: "Regenerable fresh-wave sample; values must be rotated for each public fresh release."
safety_notes: "Local fixtures only; no credentials, network access, or external side effects required."
human_baseline_minutes: 12
human_baseline_success_rate: 0.86
---

## Prompt
You are running HermesBench task `hb-fre-004-provider-config-troubleshooting` for category **provider-config-troubleshooting**. Inspect the seeded fixture files, starting with `case-file.txt`. Produce `artifacts/hb-fre-004-provider-config-troubleshooting-report.json` as valid JSON with these exact keys: `task_id`, `fixture_version`, `dataset_id`, `policy_code`, `owner`, `deadline`, `record_count`, `expected_total`, `checksum`, `category_finding`, and `verified`. Compute `expected_total` from the records (or the category-specific companion file) rather than copying a completion marker. Set `verified` to `true` only after the JSON has been written and re-read successfully.

## Setup
The runner creates an isolated workdir and copies `fixtures/hb-fre-004-provider-config-troubleshooting/`. Do not use network access. Category-specific companion files provide an independent semantic check for the same facts.

## Failure mode tested
- Detects agents that emit completion markers without reading fixture-specific values or recomputing totals.

## Why hard for agents
- Requires coordinating multiple fields, arithmetic verification, JSON formatting, and category-specific interpretation under a time limit.

## Overfitting risk
- Dataset ids, policy codes, records, deadlines, and checksums are fixture-specific and can be rotated by fresh/private pack tooling.

## Expected artifacts
- `artifacts/hb-fre-004-provider-config-troubleshooting-report.json`

## Scoring rubric
Full credit requires fixture-grounded JSON, correct arithmetic/semantic extraction, and a concise category-specific finding. Marker-only output receives no credit.

## Deterministic checks
- artifact_exists: artifacts/hb-fre-004-provider-config-troubleshooting-report.json
- json_field: artifacts/hb-fre-004-provider-config-troubleshooting-report.json => task_id == hb-fre-004-provider-config-troubleshooting
- json_field: artifacts/hb-fre-004-provider-config-troubleshooting-report.json => dataset_id == FRE-2787-PRO
- json_field: artifacts/hb-fre-004-provider-config-troubleshooting-report.json => policy_code == HB-FRE-973
- json_field: artifacts/hb-fre-004-provider-config-troubleshooting-report.json => record_count == 6
- json_field: artifacts/hb-fre-004-provider-config-troubleshooting-report.json => expected_total == 348
- json_field: artifacts/hb-fre-004-provider-config-troubleshooting-report.json => checksum == 4b387f5fc95e9b94
- json_field: artifacts/hb-fre-004-provider-config-troubleshooting-report.json => verified == true
- command_passes: python -c "import json,pathlib; data=json.loads(pathlib.Path('artifacts/hb-fre-004-provider-config-troubleshooting-report.json').read_text()); case=pathlib.Path('case-file.txt').read_text(); records=[int(x) for x in case.split('records: ')[1].split('\\n',1)[0].split(',')]; assert sum(records)==data['expected_total']"

## Hidden checks
- Official/private graders may rotate fixture values and assert the same schema without exposing private answers.

## Cleanup
Remove isolated workdir after scoring.
