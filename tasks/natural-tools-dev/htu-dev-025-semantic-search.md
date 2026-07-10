---
id: htu-dev-025-semantic-search
title: Natural Tool-Use - Semantic Search Required
category: natural-tool-use
category_detail: semantic_search
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-09
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- semantic_search
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Prompt is stable. The task tests whether the agent discovers the semantic_search tool.
safety_notes: Semantic_search tool only. No external side effects beyond the configured provider.
human_baseline_minutes: 5
human_baseline_success_rate: 0.75
quality_tier: experimental
quality_notes: Tests whether the model uses the Hermes semantic_search tool to satisfy the request.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- semantic_search
---

## Prompt
Use the Hermes semantic_search tool to find files related to "deployment instructions" in the current working directory. If the tool is unavailable, write "semantic_search unavailable" to artifacts/answer.txt. Otherwise, write "semantic_search used" and the top matching file path to artifacts/answer.txt.

## Setup
No fixture required. The agent must use the semantic_search tool to attempt the request.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the semantic_search tool and writes a result to the answer file. Either a successful tool use or a clear "unavailable" fallback is acceptable for the deterministic score; behavior grading requires the tool class to be present in the transcript.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => semantic_search
- command_passes: grep -qE 'semantic_search used|semantic_search unavailable' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Answering from the prompt alone without invoking the semantic_search tool. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes exposes a semantic_search tool and attempt to call it, rather than performing the task by hand or hallucinating a result.

## Overfitting risk
Low. The scoring is behavior-focused and accepts either a successful tool use or an explicit unavailability note.

## Cleanup
Delete the isolated workdir after grading.
