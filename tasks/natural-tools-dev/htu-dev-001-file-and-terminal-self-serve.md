---
id: htu-dev-001-file-and-terminal-self-serve
title: Natural Tool-Use - File + Terminal Self-Serve
category: natural-tool-use
category_detail: file-terminal
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- terminal
- file
fixtures:
- data/records.txt
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Vague local-only task. No hidden oracle. Fixture data rotates; public prompt is stable, but the expected answer changes with the seeded numbers.
safety_notes: Credential-free local fixture. No external side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.95
quality_tier: experimental
quality_notes: Tests whether the model discovers it must read local files and run a shell command instead of answering from the prompt alone.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- file
- terminal
---

## Prompt
You are in a work directory with some files. A local user wants to know the sum of all numbers recorded in `data/records.txt`.

Do not ask the user anything. Determine what information you need, use the tools available, and give the final answer.

## Setup
The runner copies only the public fixture into an isolated workdir. No hidden oracle is used.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent actually reads the file and uses the terminal to compute the sum, and writes the correct total to `artifacts/answer.txt`. The grader ignores prose and scores the tool-use behavior plus the final answer.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => 42
- command_passes: grep -E '[0-9]+' data/records.txt
- command_contains: cat artifacts/answer.txt => 42

## Hidden checks
- No hidden checks.

## Failure mode tested
Purely textual/hallucinated answers without inspecting the fixture should fail, even if the final number happens to be correct.

## Why hard for agents
The prompt is intentionally vague and does not say "read data/records.txt" or "run a command." The model must decide to explore the workdir and use the available tools.

## Overfitting risk
Low. The answer depends on the fixture content, and the model must inspect it to be robust.

## Cleanup
Delete the isolated workdir after grading.
