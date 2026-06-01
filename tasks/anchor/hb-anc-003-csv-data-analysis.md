---
id: hb-anc-003-csv-data-analysis
title: "Stable Anchor 3: csv-data-analysis"
category: csv-data-analysis
wave: anchor-v1
visibility: public
created_at: 2026-06-01
freshness_window: stable-anchor
expected_human_minutes: 11
difficulty: medium
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 180
contamination_notes: "stable anchor; published for longitudinal/dev comparison."
safety_notes: "Local fixtures only; no credentials or external side effects."
human_baseline_minutes: 10
human_baseline_success_rate: 0.9
---

## Prompt
Complete this stable anchor HermesBench task for `csv-data-analysis`. Use the seeded local fixture, create `artifacts/hb-anc-003-csv-data-analysis.txt`, include `task_id: hb-anc-003-csv-data-analysis` and `verified: true`, and do not claim success until the artifact exists.

## Setup
The runner creates an isolated workdir and copies fixtures. Private variants can alter fixture values and hidden checks without changing the public contract.

## Expected artifacts
- artifacts/hb-anc-003-csv-data-analysis.txt

## Scoring rubric
Deterministic pass requires artifact existence and both verification markers. Hidden/private checks may add fixture-specific assertions for official runs.

## Deterministic checks
- artifact_exists: artifacts/hb-anc-003-csv-data-analysis.txt
- artifact_contains: artifacts/hb-anc-003-csv-data-analysis.txt => verified: true
- artifact_contains: artifacts/hb-anc-003-csv-data-analysis.txt => task_id: hb-anc-003-csv-data-analysis

## Hidden checks
- Future private mirror may add hidden fixture checks.

## Cleanup
Remove isolated workdir after scoring.
