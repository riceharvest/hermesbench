---
id: hb-fre-001-research-freshness
title: "Fresh Rolling 1: research-freshness"
category: research-freshness
wave: fresh-2026-06
visibility: public
created_at: 2026-06-01
freshness_window: 30 days
expected_human_minutes: 9
difficulty: medium
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 180
contamination_notes: "fresh rolling; published for longitudinal/dev comparison."
safety_notes: "Local fixtures only; no credentials or external side effects."
human_baseline_minutes: 8
human_baseline_success_rate: 0.9
---

## Prompt
Complete this fresh rolling HermesBench task for `research-freshness`. Use the seeded local fixture, create `artifacts/hb-fre-001-research-freshness.txt`, include `task_id: hb-fre-001-research-freshness` and `verified: true`, and do not claim success until the artifact exists.

## Setup
The runner creates an isolated workdir and copies fixtures. Private variants can alter fixture values and hidden checks without changing the public contract.

## Expected artifacts
- artifacts/hb-fre-001-research-freshness.txt

## Scoring rubric
Deterministic pass requires artifact existence and both verification markers. Hidden/private checks may add fixture-specific assertions for official runs.

## Deterministic checks
- artifact_exists: artifacts/hb-fre-001-research-freshness.txt
- artifact_contains: artifacts/hb-fre-001-research-freshness.txt => verified: true
- artifact_contains: artifacts/hb-fre-001-research-freshness.txt => task_id: hb-fre-001-research-freshness

## Hidden checks
- Future private mirror may add hidden fixture checks.

## Cleanup
Remove isolated workdir after scoring.
