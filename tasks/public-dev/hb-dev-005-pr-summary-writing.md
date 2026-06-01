---
id: hb-dev-005-pr-summary-writing
title: Commit message / PR summary writing
category: pr-summary-writing
wave: public-dev-2026-06
visibility: public
created_at: 2026-06-01
freshness_window: stable-anchor
expected_human_minutes: 10
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
quality_notes: Fixture-backed pr-summary-writing task requiring extraction of multiple
  deterministic facts and a category-specific artifact, not marker-only completion.
---

## Prompt
You are running HermesBench public-dev task hb-dev-005-pr-summary-writing for category **pr-summary-writing**. Inspect `case-file.txt` in the seeded fixture. Extract the domain facts fixture_version, dataset_id, policy_code, expected_total, record_count, checksum, owner, and deadline. Write `artifacts/hb-dev-005-pr-summary-writing-report.json` as JSON with those exact keys plus `task_id` and `verified: true`. This is a real fixture-backed task: do not satisfy it with generic marker text; verify the JSON fields before claiming done.

## Setup
The runner copies `fixtures/hb-dev-005-pr-summary-writing/` into an isolated workdir. Use only local fixture files; no credentials, network, or external side effects are required.

## Expected artifacts
- artifacts/hb-dev-005-pr-summary-writing-report.json

## Scoring rubric
Full credit for this pr-summary-writing task requires deterministic JSON evidence matching fixture_version, dataset_id, policy_code, expected_total, record_count, and checksum from the fixture. The grader verifies concrete fields and artifact existence; generic marker-only output receives no credit.

## Deterministic checks
- artifact_exists: artifacts/hb-dev-005-pr-summary-writing-report.json
- json_field: artifacts/hb-dev-005-pr-summary-writing-report.json => task_id=hb-dev-005-pr-summary-writing
- json_field: artifacts/hb-dev-005-pr-summary-writing-report.json => verified=true
- json_field: artifacts/hb-dev-005-pr-summary-writing-report.json => fixture_version=public-dev-v1
- json_field: artifacts/hb-dev-005-pr-summary-writing-report.json => dataset_id=public-dev-dataset-005
- json_field: artifacts/hb-dev-005-pr-summary-writing-report.json => policy_code=HB-POL-1005
- json_field: artifacts/hb-dev-005-pr-summary-writing-report.json => expected_total=48
- json_field: artifacts/hb-dev-005-pr-summary-writing-report.json => record_count=7
- json_field: artifacts/hb-dev-005-pr-summary-writing-report.json => checksum=hb005cafe

## Hidden checks
- Private holdout may assert fixture-specific facts without exposing hidden variants in public result output.

## Cleanup
Delete the isolated workdir after grading. Do not preserve secrets or transcripts outside normalized result JSON.
