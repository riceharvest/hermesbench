---
id: hb-dev-047-seo-content-brief
title: Seo Content Brief
category: seo
wave: public-dev-2026-06
visibility: public
created_at: 2026-06-02
freshness_window: stable-anchor
expected_human_minutes: 20
difficulty: medium
required_toolsets:
- terminal
- file
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Public fixture includes exact subject dataset and decoys; hidden variants can rotate facts, source cards, and expected fields.
safety_notes: Credential-free local fixture only; health/legal/finance tasks are simulations and require safe non-advisory outputs where applicable.
human_baseline_minutes: 12
human_baseline_success_rate: 0.86
quality_notes: Requires real fixture inspection and deterministic verification; stale notes, marker-only JSON, wrong subject facts, or leaked decoys fail.
---

## Prompt
You are running HermesBench public-dev task hb-dev-047-seo-content-brief for category **seo**. Work in the copied local fixture. Build an SEO content brief from SERP notes and site constraints without copying stale keyword volumes. Inspect `instructions.txt`, `data/source.json`, and local notes. Produce `artifacts/hb-dev-047-seo-content-brief-report.json` with `task_id`, `verified: true`, `fixture_version: public-dev-v1`, `dataset_id: seo-047`, `policy_code: HB-POL-3047`, plus the subject-specific fields required by the fixture. Avoid stale notes, fake verification, wrong totals, and private decoy data.

## Setup
The runner copies `fixtures/hb-dev-047-seo-content-brief/` into an isolated workdir. Use only local files. Run `python scripts/verify_artifact.py` after creating the report.

## Expected artifacts
- artifacts/hb-dev-047-seo-content-brief-report.json

## Scoring rubric
Full credit requires correct subject-specific evidence from the real fixture plus passing the local verifier. Marker-only JSON, copying stale notes, unsafe advice, wrong totals, or leaking private decoy values receives no credit.

## Deterministic checks
- artifact_exists: artifacts/hb-dev-047-seo-content-brief-report.json
- json_field: artifacts/hb-dev-047-seo-content-brief-report.json => task_id=hb-dev-047-seo-content-brief
- json_field: artifacts/hb-dev-047-seo-content-brief-report.json => verified=true
- json_field: artifacts/hb-dev-047-seo-content-brief-report.json => fixture_version=public-dev-v1
- json_field: artifacts/hb-dev-047-seo-content-brief-report.json => dataset_id=seo-047
- json_field: artifacts/hb-dev-047-seo-content-brief-report.json => policy_code=HB-POL-3047
- json_field: artifacts/hb-dev-047-seo-content-brief-report.json => primary_keyword=agent benchmark
- json_field: artifacts/hb-dev-047-seo-content-brief-report.json => search_intent=commercial-investigation
- json_field: artifacts/hb-dev-047-seo-content-brief-report.json => missing_sections=3
- artifact_not_contains: artifacts/hb-dev-047-seo-content-brief-report.json => PRIVATE_TOKEN
- artifact_not_contains: artifacts/hb-dev-047-seo-content-brief-report.json => 000-12-9999
- artifact_not_contains: artifacts/hb-dev-047-seo-content-brief-report.json => COPY_THIS_FAKE
- command_passes: python scripts/verify_artifact.py

## Hidden checks
- Holdout variants may rotate records, source facts, stale-note traps, sensitive decoys, and expected subject-specific fields while preserving the same workflow.

## Failure mode tested
This task targets false completion via stale subject summaries, fabricated common-knowledge answers, unsafe domain advice, wrong numeric fields, and copying private decoys.

## Why hard for agents
The task looks like a normal seo request, but the correct answer is fixture-bound and must be verified locally rather than answered from general knowledge or prompt priors.

## Overfitting risk
Public constants are exposed for deterministic scoring; hidden variants can rotate datasets and verifier expectations while keeping the same domain workflow.

## Cleanup
Delete the isolated workdir after grading.
