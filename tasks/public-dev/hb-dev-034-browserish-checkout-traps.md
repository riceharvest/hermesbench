---
id: hb-dev-034-browserish-checkout-traps
title: Browser-ish return workflow traps
category: browser-ish-workflow
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
contamination_notes: Public static-site fixture includes a misleading default checkbox and exact preview JSON; private variants can rotate order ids and trap fields.
safety_notes: Local static HTML/JSON only; no real browser, payment, or customer system.
human_baseline_minutes: 10
human_baseline_success_rate: 0.86
quality_notes: Browser-like workflow requires inspecting multiple local files and avoiding the visible default trap; checks verify concrete fields.
---

## Prompt
You are running HermesBench public-dev task hb-dev-034-browserish-checkout-traps for category **browser-ish-workflow**. Complete the local static return workflow by inspecting `site/` and `instructions.txt`. Trap: the form's visible default is store credit, but the customer needs original-card refund and prepaid label. Write `artifacts/hb-dev-034-browserish-checkout-traps-report.json` with `task_id`, `verified: true`, `fixture_version: public-dev-v1`, `dataset_id: return-flow-034`, `policy_code: HB-POL-2034`, `order: RMA-8831`, `confirmation_code: RET-64Q9`, `refund_method: original_card`, `label: prepaid`, `restocking_fee: 0`, `record_count: 5`, and `checksum: hb034ui`.

## Setup
The runner copies `fixtures/hb-dev-034-browserish-checkout-traps/` into an isolated workdir. No external browser is required; inspect the local HTML and JSON files directly.

## Expected artifacts
- artifacts/hb-dev-034-browserish-checkout-traps-report.json

## Scoring rubric
Full credit requires following the browser-ish workflow and avoiding the trap field. Deterministic checks verify exact order, confirmation code, refund method, label, policy code, record count, and checksum; marker text or selecting store credit fails.

## Deterministic checks
- artifact_exists: artifacts/hb-dev-034-browserish-checkout-traps-report.json
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => task_id=hb-dev-034-browserish-checkout-traps
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => verified=true
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => fixture_version=public-dev-v1
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => dataset_id=return-flow-034
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => policy_code=HB-POL-2034
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => order=RMA-8831
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => confirmation_code=RET-64Q9
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => refund_method=original_card
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => label=prepaid
- json_field: artifacts/hb-dev-034-browserish-checkout-traps-report.json => checksum=hb034ui

## Hidden checks
- Holdout variants may alter the visible default trap and confirmation details.

## Cleanup
Delete the isolated workdir after grading.
