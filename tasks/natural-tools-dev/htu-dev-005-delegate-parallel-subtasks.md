---
id: htu-dev-005-delegate-parallel-subtasks
title: Natural Tool-Use - Delegate Parallel Subtasks
category: natural-tool-use
category_detail: delegation
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- delegation
- terminal
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Public prompt is stable; the two file names and values are fixed but arbitrary.
safety_notes: Local subagents only. No external side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.80
quality_tier: experimental
quality_notes: Tests whether the model delegates parallel subtasks to subagents instead of solving sequentially in the main agent.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- delegation
---

## Prompt
You need to know the sum of numbers in `data/a.txt` and `data/b.txt`. The two files are independent. Use parallel subagents to compute each partial sum, then combine the results and write the total to `artifacts/answer.txt`.

## Setup
The runner copies only the public fixtures into an isolated workdir.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses `delegate_task` at least once and writes the correct combined sum. The grader checks the delegation tool call and the final answer.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: grep -qE '(^|[^0-9])50($|[^0-9])' artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => 50
- command_contains: cat artifacts/answer.txt => 50

## Hidden checks
- No hidden checks.

## Failure mode tested
Reading and summing both files in the main agent thread without delegation. The task rewards discovering and using the delegation feature.

## Why hard for agents
The model must recognize the parallel structure, understand that Hermes has a subagent tool, and route subtasks correctly.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
