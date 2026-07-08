---
id: htu-dev-010-clarify-ambiguous
title: Natural Tool-Use - Clarify Ambiguous Request
category: natural-tool-use
category_detail: clarify
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- clarify
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Static local fixture. Public prompt is stable; the seed value is fixed.
safety_notes: Clarify tool and local file only. No external side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.80
quality_tier: experimental
quality_notes: Tests whether the model asks for clarification before proceeding on an ambiguous task. Requires a harness that can provide a clarifying user response or accept the fallback.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- clarify
---

## Prompt
I need you to write a configuration file, but the format is ambiguous. Use the Hermes clarify tool to ask me which format I want. If the tool is unavailable or you do not get a response, default to JSON and write `{"ok": true}` to `artifacts/answer.txt`.

## Setup
The runner copies the public fixture into the workdir. The fixture `case/response.txt` is provided for reference; the agent should still use the clarify tool first.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the clarify tool and produces a valid JSON file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- command_passes: python3 -c "import json; json.load(open('artifacts/answer.txt'))"
- artifact_contains: artifacts/answer.txt => ok

## Hidden checks
- No hidden checks.

## Failure mode tested
Making an arbitrary choice without asking for clarification. The task forces use of the clarify tool.

## Why hard for agents
The model must decide that ambiguity requires user interaction and use the correct tool.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
