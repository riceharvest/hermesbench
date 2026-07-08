---
id: htu-dev-012-computer-use
title: Natural Tool-Use - Computer Use
category: natural-tool-use
category_detail: computer_use
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- computer_use
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Public prompt is stable; the artifact content depends on the desktop environment.
safety_notes: Computer use tool only. Captures the local desktop; no external side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.70
quality_tier: experimental
quality_notes: Tests whether the model uses the computer_use tool to interact with the desktop. Requires a desktop environment.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- computer_use
---

## Prompt
Use the Hermes computer_use tool to capture the current desktop and save it to `artifacts/screenshot.png`. Then write the name of the tool you used (or "computer_use unavailable") to `artifacts/answer.txt`.

## Setup
No fixture required. This task requires a desktop environment and may be skipped if unavailable.

## Expected artifacts
- artifacts/answer.txt
- artifacts/screenshot.png (when the desktop environment is available)

## Scoring rubric
Pass if the agent uses the computer_use tool and writes a result to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => computer_use
- command_passes: grep -qE 'computer_use|screenshot' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Writing the answer without attempting to use the desktop automation tool.

## Why hard for agents
The model must decide to use a desktop automation tool and handle the case where it is unavailable.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
