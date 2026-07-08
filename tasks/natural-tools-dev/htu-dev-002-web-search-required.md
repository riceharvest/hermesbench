---
id: htu-dev-002-web-search-required
title: Natural Tool-Use - Web Search Required
category: natural-tool-use
category_detail: web
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: rolling
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- web
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Open-ended fact that changes over time and is not in the fixture. Public prompt is stable but the correct answer changes, so contamination is limited.
safety_notes: Web search only. No credentials or side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.90
quality_tier: experimental
quality_notes: Tests whether the model decides to use web search instead of hallucinating a current fact.
requires_skills: false
coding_required: false
external_web: true
tool_use_requirements:
- web
---

## Prompt
What is the current version of the latest stable release of the Hermes Agent framework? Write the version string to `artifacts/answer.txt`.

Do not guess. Use the tools available to find the current answer.

## Setup
No fixture required. The agent must use web search to discover the current version.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent performed a web search and wrote a plausible version string. The grader checks the presence of a web search tool call and a non-empty answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- command_contains: cat artifacts/answer.txt => v
- command_not_contains: cat artifacts/answer.txt => unknown

## Hidden checks
- No hidden checks.

## Failure mode tested
Hallucinating a version without searching. The agent must recognize that a current external fact requires a web tool.

## Why hard for agents
The prompt is a simple factual question, but the answer is not knowable from the context window. The model must decide to search.

## Overfitting risk
Low. The version string changes, and the scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
