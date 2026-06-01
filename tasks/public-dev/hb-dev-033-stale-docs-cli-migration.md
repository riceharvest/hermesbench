---
id: hb-dev-033-stale-docs-cli-migration
title: Stale docs CLI migration
category: stale-docs
wave: public-dev-2026-06
visibility: public
created_at: 2026-06-01
freshness_window: stable-anchor
expected_human_minutes: 18
difficulty: hard
required_toolsets:
- terminal
- file
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Public fixture combines stale quickstart with changelog and CLI help; private variants can rotate command names and flag migrations.
safety_notes: Documentation-only local fixture; no commands need contact external services.
human_baseline_minutes: 9
human_baseline_success_rate: 0.9
quality_notes: Requires detecting stale docs and synthesizing the current command from multiple fixture files with JSON evidence.
---

## Prompt
You are running HermesBench public-dev task hb-dev-033-stale-docs-cli-migration for category **stale-docs**. The quickstart is stale. Compare `docs/quickstart.md`, `CHANGELOG.md`, `cli_help.txt`, and `config/workspaces.yaml`. Write an updated doc `artifacts/quickstart-fixed.md` and a JSON report `artifacts/hb-dev-033-stale-docs-cli-migration-report.json` with `task_id`, `verified: true`, `fixture_version: public-dev-v1`, `dataset_id: cli-docs-033`, `policy_code: HB-POL-2033`, `old_command: acme sync`, `new_command: acmectl replicate`, `workspace: ws-northstar`, `window: 12h`, `checksum: hb033doc`, and `record_count: 4`.

## Setup
The runner copies `fixtures/hb-dev-033-stale-docs-cli-migration/` into an isolated workdir. Use only the local docs/config fixture.

## Expected artifacts
- artifacts/quickstart-fixed.md
- artifacts/hb-dev-033-stale-docs-cli-migration-report.json

## Scoring rubric
Full credit requires fixing the stale documentation to use the current CLI and flags while preserving the fixture's workspace/window facts. Deterministic checks verify the artifact, dataset id, policy code, command migration, and checksum; generic stale-docs commentary receives no credit.

## Deterministic checks
- artifact_exists: artifacts/quickstart-fixed.md
- artifact_contains: artifacts/quickstart-fixed.md => acmectl replicate --workspace ws-northstar --window 12h --output artifacts/sync-report.json --dry-run
- artifact_exists: artifacts/hb-dev-033-stale-docs-cli-migration-report.json
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => task_id=hb-dev-033-stale-docs-cli-migration
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => verified=true
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => fixture_version=public-dev-v1
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => dataset_id=cli-docs-033
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => policy_code=HB-POL-2033
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => old_command=acme sync
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => new_command=acmectl replicate
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => workspace=ws-northstar
- json_field: artifacts/hb-dev-033-stale-docs-cli-migration-report.json => checksum=hb033doc

- command_passes: python scripts/verify_artifact.py

## Hidden checks
- Holdout variants may rotate current command and flag names while retaining a stale quickstart trap.

## Failure mode tested
This task rejects marker-only completion, stale fixture copying, wrong deterministic fields, and leaked trap/private-looking data by requiring a local verifier in addition to field checks.

## Why hard for agents
The agent must inspect the fixture and produce a coherent artifact that survives executable validation rather than only echoing the visible task id or verified marker.

## Overfitting risk
Public constants are visible for development; hidden variants can rotate fixture values, file names, decoy markers, and verifier expectations while preserving the same workflow.

## Cleanup
Delete the isolated workdir after grading.
