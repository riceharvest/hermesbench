---
id: hb-dev-032-ambiguous-log-root-cause
title: Ambiguous log root cause analysis
category: ambiguous-logs
wave: public-dev-2026-06
visibility: public
created_at: 2026-06-01
freshness_window: stable-anchor
expected_human_minutes: 20
difficulty: hard
required_toolsets:
- terminal
- file
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Public log fixture has trace-specific misleading errors; private variants can rotate trace ids, services, and root-cause taxonomy.
safety_notes: Local text logs only; no production systems or network access.
human_baseline_minutes: 10
human_baseline_success_rate: 0.88
quality_notes: Requires correlating ambiguous logs by trace id and first divergent event; deterministic checks verify concrete analysis fields.
---

## Prompt
You are running HermesBench public-dev task hb-dev-032-ambiguous-log-root-cause for category **ambiguous-logs**. Inspect the local logs and runbook. Do not pick the earliest ERROR blindly. Produce `artifacts/hb-dev-032-ambiguous-log-root-cause-report.json` with `task_id`, `verified: true`, `fixture_version: public-dev-v1`, `dataset_id: checkout-logs-032`, `incident_id: INC-3209`, `policy_code: HB-POL-2032`, `root_trace: tr-a17`, `root_cause: payment_contract_mismatch`, `false_lead: db_pool_exhausted`, `record_count: 13`, and `checksum: hb03291d`.

## Setup
The runner copies `fixtures/hb-dev-032-ambiguous-log-root-cause/` into an isolated workdir. Use local files under `logs/` plus `runbook.md`.

## Expected artifacts
- artifacts/hb-dev-032-ambiguous-log-root-cause-report.json

## Scoring rubric
Full credit requires evidence that the ambiguous logs were correlated correctly: the grader verifies the incident id, root trace, root cause, false lead, policy code, record count, and checksum. A generic summary or earliest-error answer is insufficient.

## Deterministic checks
- artifact_exists: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => task_id=hb-dev-032-ambiguous-log-root-cause
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => verified=true
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => fixture_version=public-dev-v1
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => dataset_id=checkout-logs-032
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => incident_id=INC-3209
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => policy_code=HB-POL-2032
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => root_trace=tr-a17
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => root_cause=payment_contract_mismatch
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => false_lead=db_pool_exhausted
- json_field: artifacts/hb-dev-032-ambiguous-log-root-cause-report.json => checksum=hb03291d

## Hidden checks
- Holdout variants may include noisy errors and require the same trace-correlation discipline.

## Cleanup
Delete the isolated workdir after grading.
