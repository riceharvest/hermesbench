---
id: hb-dev-029-tool-call-planning
title: Tool-call planning
category: tool-call-planning
wave: public-dev-2026-06
visibility: public
created_at: 2026-06-01
freshness_window: stable-anchor
expected_human_minutes: 7
difficulty: hard
required_toolsets:
- terminal
- file
grading_type: deterministic
timeout_seconds: 120
contamination_notes: Public dev task with fixture-specific values; private/fresh waves
  must rotate dataset_id, policy_code, expected_total, and checksum to prevent marker
  memorization.
safety_notes: Uses local fixtures only; no credentials or external side effects.
human_baseline_minutes: 9
human_baseline_success_rate: 0.95
quality_notes: Fixture-backed tool-call-planning task requiring extraction of multiple
  deterministic facts and a category-specific artifact, not marker-only completion.
---

## Prompt
You are running HermesBench public-dev task hb-dev-029-tool-call-planning for category **tool-call-planning**. Inspect `case-file.txt` in the seeded fixture. Extract the domain facts fixture_version, dataset_id, policy_code, expected_total, record_count, checksum, owner, and deadline. Write `artifacts/hb-dev-029-tool-call-planning-report.json` as JSON with those exact keys plus `task_id` and `verified: true`. This is a real fixture-backed task: do not satisfy it with generic marker text; verify the JSON fields before claiming done.

## Setup
The runner copies `fixtures/hb-dev-029-tool-call-planning/` into an isolated workdir. Use only local fixture files; no credentials, network, or external side effects are required.

## Expected artifacts
- artifacts/hb-dev-029-tool-call-planning-report.json

## Scoring rubric
Full credit for this tool-call-planning task requires deterministic JSON evidence matching fixture_version, dataset_id, policy_code, expected_total, record_count, and checksum from the fixture. The grader verifies concrete fields and artifact existence; generic marker-only output receives no credit.

## Deterministic checks
- artifact_exists: artifacts/hb-dev-029-tool-call-planning-report.json
- json_field: artifacts/hb-dev-029-tool-call-planning-report.json => task_id=hb-dev-029-tool-call-planning
- json_field: artifacts/hb-dev-029-tool-call-planning-report.json => verified=true
- json_field: artifacts/hb-dev-029-tool-call-planning-report.json => fixture_version=public-dev-v1
- json_field: artifacts/hb-dev-029-tool-call-planning-report.json => dataset_id=public-dev-dataset-029
- json_field: artifacts/hb-dev-029-tool-call-planning-report.json => policy_code=HB-POL-1029
- json_field: artifacts/hb-dev-029-tool-call-planning-report.json => expected_total=216
- json_field: artifacts/hb-dev-029-tool-call-planning-report.json => record_count=31
- json_field: artifacts/hb-dev-029-tool-call-planning-report.json => checksum=hb029cafe

- command_passes: python scripts/verify_artifact.py

## Hidden checks
- Private holdout may assert fixture-specific facts without exposing hidden variants in public result output.

## Failure mode tested
This task rejects marker-only completion, stale fixture copying, wrong deterministic fields, and leaked trap/private-looking data by requiring a local verifier in addition to field checks.

## Why hard for agents
The agent must inspect the fixture and produce a coherent artifact that survives executable validation rather than only echoing the visible task id or verified marker.

## Overfitting risk
Public constants are visible for development; hidden variants can rotate fixture values, file names, decoy markers, and verifier expectations while preserving the same workflow.

## Cleanup
Delete the isolated workdir after grading. Do not preserve secrets or transcripts outside normalized result JSON.
