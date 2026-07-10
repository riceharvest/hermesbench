---
id: htu-dev-007-code-execution
title: Natural Tool-Use - Code Execution
category: natural-tool-use
category_detail: code_execution
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- code_execution
- file
fixtures:
- case/numbers.txt
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Static local fixture. Public prompt is stable; the fixture value is fixed.
safety_notes: Local file and code execution tool only. No side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.85
quality_notes: Tests whether the model uses the sandboxed code execution tool instead of shelling out.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- code_execution
---

## Prompt
The file `case/numbers.txt` contains a list of numbers, one per line. Use the Hermes code execution tool to compute the sum of these numbers and write the sum to `artifacts/answer.txt`. Do not use the terminal tool.

## Setup
The runner copies the public fixture into the workdir.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the code execution tool and writes the correct sum.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => 42
- command_contains: cat artifacts/answer.txt => 42

## Hidden checks
- No hidden checks.

## Failure mode tested
Writing a shell command instead of using the sandboxed code execution tool. The task specifically tests tool discovery.

## Why hard for agents
The model must know that Hermes has a dedicated code execution tool and choose it over the terminal.

## Overfitting risk
Low. The scoring is behavior-focused and the fixture value is arbitrary.

## Cleanup
Delete the isolated workdir after grading.
