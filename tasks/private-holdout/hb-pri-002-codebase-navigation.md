---
id: hb-pri-002-codebase-navigation
title: "Private Hidden Holdout 2: codebase-navigation"
category: codebase-navigation
wave: holdout
visibility: private
created_at: 2026-06-01
freshness_window: private-holdout
expected_human_minutes: 10
difficulty: medium
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 180
contamination_notes: "private hidden holdout; not published in official prompt packs."
safety_notes: "Local fixtures only; no credentials or external side effects."
human_baseline_minutes: 9
human_baseline_success_rate: 0.9
---

## Prompt
Complete this private hidden holdout HermesBench task for `codebase-navigation`. Use the seeded local fixture, create `artifacts/hb-pri-002-codebase-navigation.txt`, include `task_id: hb-pri-002-codebase-navigation` and `verified: true`, and do not claim success until the artifact exists.

## Setup
The runner creates an isolated workdir and copies fixtures. Private variants can alter fixture values and hidden checks without changing the public contract.

## Expected artifacts
- artifacts/hb-pri-002-codebase-navigation.txt

## Scoring rubric
Deterministic pass requires artifact existence and both verification markers. Hidden/private checks may add fixture-specific assertions for official runs.

## Deterministic checks
- artifact_exists: artifacts/hb-pri-002-codebase-navigation.txt
- artifact_contains: artifacts/hb-pri-002-codebase-navigation.txt => verified: true
- artifact_contains: artifacts/hb-pri-002-codebase-navigation.txt => task_id: hb-pri-002-codebase-navigation

## Hidden checks
- Maintainer-only hidden checks assert changed fixture details and must not be printed in public results.

## Cleanup
Remove isolated workdir after scoring.
