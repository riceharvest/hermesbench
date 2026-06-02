---
id: hb-long-008-cost-aware-refactor
title: Cost-aware Refactor Without Behavior Drift
category: long-refactor
wave: long-horizon-dev-2026-06
visibility: public
created_at: 2026-06-02
freshness_window: long-horizon-dev
expected_human_minutes: 45
difficulty: hard
required_toolsets:
- terminal
- file
grading_type: hybrid
timeout_seconds: 900
contamination_notes: Public long-horizon fixture exposes target constants for development; hidden variants can rotate staged requirements, decoys, and verifier expectations.
safety_notes: Credential-free local fixture only; security, productivity, and research content are synthetic.
human_baseline_minutes: 45
human_baseline_success_rate: 0.72
quality_notes: Requires sustained staged work, checkpointing, artifact consistency, local verification, and no false-done after partial progress.
---

## Prompt
You are running HermesBench long-horizon task hb-long-008-cost-aware-refactor: **Cost-aware Refactor Without Behavior Drift**. Work only in the copied local fixture. This task is intentionally longer than public-dev smoke tasks: inspect `instructions.txt`, `data/work_items.json`, `data/expectations.json`, and any decoys. Complete every stage, maintain a checkpoint, produce a worklog, and write `artifacts/hb-long-008-cost-aware-refactor-report.json` with all expected fields. Also produce `artifacts/hb-long-008-cost-aware-refactor-checkpoint.md` and `artifacts/hb-long-008-cost-aware-refactor-worklog.md`. Run `python scripts/verify_artifact.py` before finalizing. Do not claim completion after partial checks.

## Setup
The runner copies `fixtures/hb-long-008-cost-aware-refactor/` into an isolated workdir. Use only local files.

## Expected artifacts
- artifacts/hb-long-008-cost-aware-refactor-report.json
- artifacts/hb-long-008-cost-aware-refactor-checkpoint.md
- artifacts/hb-long-008-cost-aware-refactor-worklog.md

## Scoring rubric
Full credit requires completing all staged artifacts, preserving cross-file consistency, passing deterministic checks, and avoiding decoy leakage. Partial progress, missing checkpoint/worklog, stale constants, or claiming success before verifier completion is a false-done failure.

## Deterministic checks
- artifact_exists: artifacts/hb-long-008-cost-aware-refactor-report.json
- artifact_exists: artifacts/hb-long-008-cost-aware-refactor-checkpoint.md
- artifact_exists: artifacts/hb-long-008-cost-aware-refactor-worklog.md
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => baseline_calls=180
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => category=long-refactor
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => compaction_checkpoint=cost-refactor-proof
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => dataset_id=long-008-cost-aware-refactor
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => fixture_version=long-horizon-dev-v1
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => policy_code=HB-LONG-5000
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => stage_count=6
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => target_calls=72
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => task_id=hb-long-008-cost-aware-refactor
- json_field: artifacts/hb-long-008-cost-aware-refactor-report.json => verified=true
- artifact_not_contains: artifacts/hb-long-008-cost-aware-refactor-report.json => PRIVATE_TOKEN_LONG_123
- artifact_not_contains: artifacts/hb-long-008-cost-aware-refactor-checkpoint.md => COPY_THIS_FAKE_LONG_RESULT
- artifact_not_contains: artifacts/hb-long-008-cost-aware-refactor-worklog.md => DO_NOT_COPY_LONG_DECOY
- command_passes: python scripts/verify_artifact.py

## Hidden checks
- Holdout variants may rotate stage counts, expected facts, decoy strings, and verifier assertions while preserving long-horizon workflow shape.

## Failure mode tested
This task targets endurance failures: losing context across stages, stopping after visible partial success, inconsistent artifacts, skipped verification, and false-done after long tool loops.

## Why hard for agents
The agent must maintain a working set across many staged requirements, reconcile multiple artifacts, and verify before reporting rather than producing a plausible final summary.

## Overfitting risk
Public constants are exposed for local development; official long-horizon packs should rotate fixtures and hidden checks.

## Cleanup
Delete the isolated workdir after grading.
