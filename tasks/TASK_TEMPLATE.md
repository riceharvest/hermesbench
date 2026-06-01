---
id: hb-dev-000-example
title: Example task
category: sanity-basic-tool-use
wave: public-dev-YYYY-MM
visibility: public
created_at: YYYY-MM-DD
freshness_window: stable-anchor
expected_human_minutes: 10
difficulty: easy
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 300
contamination_notes: Explain public/private risk.
safety_notes: Explain local-only scope.
quality_tier: experimental
---

## Prompt

## Setup

## Failure mode tested
Describe the specific agent failure this task detects (for example: shallow file creation, failure to inspect fixtures, false-done claims, brittle parsing, or missing verification).

## Why hard for agents
Explain why a competent human finds it straightforward while agents may struggle, including tool use, context, ambiguity, or multi-step dependencies.

## Overfitting risk
State which visible markers could be gamed and how deterministic/hidden checks reduce prompt- or fixture-specific shortcuts.

## Expected artifacts
- artifacts/example.txt

## Scoring rubric

## Deterministic checks
- artifact_exists: artifacts/example.txt
- artifact_contains: artifacts/example.txt => substantive expected value
- command_passes: test -s artifacts/example.txt
- command_not_contains: cat artifacts/example.txt => TODO_PLACEHOLDER

## Hidden checks

## Cleanup
