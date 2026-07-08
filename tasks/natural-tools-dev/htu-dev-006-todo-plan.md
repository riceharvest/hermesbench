---
id: htu-dev-006-todo-plan
title: Natural Tool-Use - Plan with Todo
category: natural-tool-use
category_detail: todo
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- todo
- file
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Static local fixture. Public prompt is stable; the fixture value is fixed.
safety_notes: Local file and todo tool only. No side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.85
quality_notes: Tests whether the model breaks a simple task into todo items and tracks progress.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- todo
---

## Prompt
The file `case/task.txt` contains a single word. Use the Hermes todo tool to create a plan with at least two steps: (1) read the input file, (2) write the word to `artifacts/answer.txt`. Complete the todo items, then write the word to `artifacts/answer.txt`.

## Setup
The runner copies the public fixture into the workdir.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the todo tool and writes the correct word to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => pineapple
- command_contains: cat artifacts/answer.txt => pineapple

## Hidden checks
- No hidden checks.

## Failure mode tested
Solving the task without tracking it in the todo tool. The task requires the model to plan with todos.

## Why hard for agents
The model must decide that a multi-step file task benefits from explicit todo tracking.

## Overfitting risk
Low. The scoring is behavior-focused and the fixture value is arbitrary.

## Cleanup
Delete the isolated workdir after grading.
