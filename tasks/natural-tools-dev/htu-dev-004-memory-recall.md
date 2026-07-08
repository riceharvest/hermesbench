---
id: htu-dev-004-memory-recall
title: Natural Tool-Use - Memory Recall
category: natural-tool-use
category_detail: memory
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- memory
- file
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Static local fixture. Public prompt is stable; the hidden value is randomized by the harness.
safety_notes: Memory store only. No external side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.90
quality_notes: Tests whether the model recognizes that the answer must be stored in durable memory and recalled later.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- memory
---

## Prompt
The user will tell you a secret word. Remember it, then later the user will ask for it back. When asked, write the secret word to `artifacts/answer.txt`.

In this benchmark run, the secret word is in `case/secret.txt`. Read it, store it in memory, then produce the answer file.

## Setup
The runner copies only the public fixture into an isolated workdir.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the memory tool to store the secret and later recall it (or at least uses memory in the transcript) and writes it to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: grep -q "benchmark-secret" artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Answering directly from the context window without storing the value in memory. The task forces use of the memory tool.

## Why hard for agents
The prompt is conversational and low-context. The model must decide that durable memory is the right feature.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
