---
id: hb-dev-015-cron-scheduling
title: "Cron/scheduling task"
category: cron-scheduling
wave: public-dev-2026-06
visibility: public
created_at: 2026-06-01
freshness_window: stable-anchor
expected_human_minutes: 11
difficulty: easy
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 120
contamination_notes: "Public dev task; safe for iteration; private wave should vary fixture values."
safety_notes: "Uses local fixtures only; no credentials or external side effects."
human_baseline_minutes: 11
human_baseline_success_rate: 0.95
---

## Prompt
You are running HermesBench public-dev task hb-dev-015-cron-scheduling. Complete the local task for category **cron-scheduling**. Complete the category-specific local workflow for `cron-scheduling` using only seeded fixtures and deterministic verification. Produce the requested artifact, and verify it before claiming done. The required final artifact is `artifacts/hb-dev-015-cron-scheduling.txt` and it must include the exact marker `verified: true` plus `task_id: hb-dev-015-cron-scheduling`.

## Setup
The runner creates an isolated temporary workdir and copies `fixtures/hb-dev-015-cron-scheduling/` when present. This public task is credential-free and deterministic. Hidden/private variants may change fixture details while preserving the contract.

## Expected artifacts
- artifacts/hb-dev-015-cron-scheduling.txt

## Scoring rubric
Full credit requires the artifact to exist and include both required markers. Partial credit is possible only in future hybrid/judge variants; this public task uses deterministic scoring.

## Deterministic checks
- artifact_exists: artifacts/hb-dev-015-cron-scheduling.txt
- artifact_contains: artifacts/hb-dev-015-cron-scheduling.txt => verified: true
- artifact_contains: artifacts/hb-dev-015-cron-scheduling.txt => task_id: hb-dev-015-cron-scheduling

## Hidden checks
- Private holdout may assert fixture-specific facts without exposing them in public output.

## Cleanup
Delete the isolated workdir after grading. Do not preserve secrets or transcripts outside normalized result JSON.
