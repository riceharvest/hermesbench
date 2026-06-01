---
id: hb-dev-031-multifile-invoice-bugfix
title: Multi-file invoice total bugfix
category: multi-file-bugfix
wave: public-dev-2026-06
visibility: public
created_at: 2026-06-01
freshness_window: stable-anchor
expected_human_minutes: 25
difficulty: hard
required_toolsets:
- terminal
- file
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Public fixture contains concrete invoice ids, customer totals, and policy ordering; private variants can rotate rows, discounts, and expected totals.
safety_notes: Local Python fixture only; no network, credentials, or external services.
human_baseline_minutes: 14
human_baseline_success_rate: 0.85
quality_notes: Requires reading multiple source files, fixing a real calculation bug, and producing deterministic JSON evidence rather than marker text.
---

## Prompt
You are running HermesBench public-dev task hb-dev-031-multifile-invoice-bugfix for category **multi-file-bugfix**. The seeded fixture is a small Python billing package. Use TDD: run the included failing test, fix the calculation so invoice policy is honored across the loader/rules/report flow, then write `artifacts/hb-dev-031-multifile-invoice-bugfix-report.json` with `task_id`, `verified: true`, `fixture_version: public-dev-v1`, `dataset_id: invoice-ledger-031`, `policy_code: HB-POL-2031`, `expected_total: 574.50`, `record_count: 5`, `checksum: hb031b17`, and `fixed_rule: discount_before_tax`.

## Setup
The runner copies `fixtures/hb-dev-031-multifile-invoice-bugfix/` into an isolated workdir. Use only local fixture files. Run `python -m pytest tests/test_invoice_totals.py` after your fix.

## Expected artifacts
- artifacts/hb-dev-031-multifile-invoice-bugfix-report.json

## Scoring rubric
Full credit requires a working multi-file bugfix verified by the provided test and JSON evidence matching the fixture facts. Generic marker output or changing the test expectation without correcting the implementation receives no credit.

## Deterministic checks
- artifact_exists: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json
- json_field: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json => task_id=hb-dev-031-multifile-invoice-bugfix
- json_field: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json => verified=true
- json_field: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json => fixture_version=public-dev-v1
- json_field: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json => dataset_id=invoice-ledger-031
- json_field: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json => policy_code=HB-POL-2031
- json_field: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json => expected_total=574.50
- json_field: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json => record_count=5
- json_field: artifacts/hb-dev-031-multifile-invoice-bugfix-report.json => checksum=hb031b17
- command_passes: python -m pytest -q tests/test_invoice_totals.py

## Hidden checks
- Holdout variants may rotate invoice values and verify the implementation rather than the public total.

## Cleanup
Delete the isolated workdir after grading.
