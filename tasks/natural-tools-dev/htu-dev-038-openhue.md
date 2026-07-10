---
id: htu-dev-038-openhue
title: Natural Tool-Use - OpenHue Light Required
category: natural-tool-use
category_detail: openhue
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-09
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- openhue
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Prompt is stable. The task tests whether the agent discovers the OpenHue skill/tool integration.
safety_notes: OpenHue tool only. No external side effects beyond the configured bridge.
human_baseline_minutes: 5
human_baseline_success_rate: 0.75
quality_tier: experimental
quality_notes: Tests whether the model uses the Hermes OpenHue skill/tool to satisfy the request.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- openhue
---

## Prompt
Use the Hermes OpenHue tool to list the configured light names. If the tool is unavailable, write "openhue unavailable" to artifacts/answer.txt. Otherwise, write "openhue used" and the number of lights to artifacts/answer.txt.

## Setup
No fixture required. The agent must use the OpenHue tool to attempt the request.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the openhue tool and writes a result to the answer file. Either a successful tool use or a clear "unavailable" fallback is acceptable for the deterministic score; behavior grading requires the tool class to be present in the transcript.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => openhue
- command_passes: grep -qE 'openhue used|openhue unavailable' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Answering from the prompt alone without invoking the OpenHue tool. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes exposes an OpenHue integration and attempt to call it, rather than performing the task by hand or hallucinating a result.

## Overfitting risk
Low. The scoring is behavior-focused and accepts either a successful tool use or an explicit unavailability note.

## Cleanup
Delete the isolated workdir after grading.
