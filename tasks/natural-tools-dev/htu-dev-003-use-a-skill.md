---
id: htu-dev-003-use-a-skill
title: Natural Tool-Use - Use a Skill
category: natural-tool-use
category_detail: skills
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- skills
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Static local fixture plus a well-known public skill. Public prompt is stable; the skill itself may evolve, but the answer is contained in the fixture.
safety_notes: Local fixture and public skill lookup only. No side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.85
quality_tier: experimental
quality_notes: Tests whether the model decides to load a relevant skill to interpret a local artifact.
requires_skills: true
coding_required: false
external_web: false
tool_use_requirements:
- skills
---

## Prompt
The file `case/artifact` contains a base64-encoded string. Decode it and write the result to `artifacts/answer.txt`.

You do not need to write decoding code. Find the appropriate Hermes skill and use it.

## Setup
The runner copies only the public fixture into an isolated workdir.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent loads a skill (e.g., `base64` or a relevant utility skill) and uses it to decode the file. The grader checks the skill tool call and the decoded output.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => decoded-by-skill
- command_contains: cat artifacts/answer.txt => decoded-by-skill

## Hidden checks
- No hidden checks.

## Failure mode tested
Writing a Python one-liner instead of using the provided skill system. The task specifically tests feature discovery, not coding ability.

## Why hard for agents
The model must know that Hermes has a skills system, search/browse for a skill, and load it.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
