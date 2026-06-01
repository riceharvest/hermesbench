---
id: hb-pri-004-provider-config-troubleshooting
title: "Private Hidden Holdout 4: provider-config-troubleshooting"
category: provider-config-troubleshooting
wave: holdout
visibility: private
created_at: 2026-06-01
freshness_window: private-holdout
expected_human_minutes: 12
difficulty: medium
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 180
contamination_notes: "private hidden holdout; not published in official prompt packs."
safety_notes: "Local fixtures only; no credentials or external side effects."
human_baseline_minutes: 11
human_baseline_success_rate: 0.9
---

## Prompt
Complete this private hidden holdout HermesBench task for `provider-config-troubleshooting`. Use the seeded local fixture, create `artifacts/hb-pri-004-provider-config-troubleshooting.txt`, include `task_id: hb-pri-004-provider-config-troubleshooting` and `verified: true`, and do not claim success until the artifact exists.

## Setup
The runner creates an isolated workdir and copies fixtures. Private variants can alter fixture values and hidden checks without changing the public contract.

## Expected artifacts
- artifacts/hb-pri-004-provider-config-troubleshooting.txt

## Scoring rubric
Deterministic pass requires artifact existence and both verification markers. Hidden/private checks may add fixture-specific assertions for official runs.

## Deterministic checks
- artifact_exists: artifacts/hb-pri-004-provider-config-troubleshooting.txt
- artifact_contains: artifacts/hb-pri-004-provider-config-troubleshooting.txt => verified: true
- artifact_contains: artifacts/hb-pri-004-provider-config-troubleshooting.txt => task_id: hb-pri-004-provider-config-troubleshooting

## Hidden checks
- Maintainer-only hidden checks assert changed fixture details and must not be printed in public results.

## Cleanup
Remove isolated workdir after scoring.
