---
id: htu-dev-009-session-search
title: Natural Tool-Use - Session Search
category: natural-tool-use
category_detail: session_search
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- session_search
- file
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Static local fixture. Public prompt is stable; the hidden value is randomized by the harness.
safety_notes: Session search only. No external side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.80
quality_notes: Tests whether the model recognizes that the answer must be retrieved from prior conversation history.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- session_search
---

## Prompt
In a previous conversation, I told you my favorite color is blue. Use the Hermes session_search tool to search your past sessions for "favorite color". Then write the color you found to `artifacts/answer.txt`. If the search returns no results, read `case/seed.txt` and use that color.

## Setup
The runner copies the public fixture into the workdir.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the session_search tool and writes a color to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => blue
- command_contains: cat artifacts/answer.txt => blue

## Hidden checks
- No hidden checks.

## Failure mode tested
Answering directly from the context window or reading the seed file without first attempting session_search.

## Why hard for agents
The model must decide that durable conversation history is the right source of the answer.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
