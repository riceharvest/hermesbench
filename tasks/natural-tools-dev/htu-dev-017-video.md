---
id: htu-dev-017-video
title: Natural Tool-Use - Video Analysis Required
category: natural-tool-use
category_detail: video
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-09
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- video
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Prompt is stable. The task tests whether the agent discovers the video tool.
safety_notes: Video tool only. No external side effects beyond the configured provider.
human_baseline_minutes: 5
human_baseline_success_rate: 0.75
quality_tier: experimental
quality_notes: Tests whether the model uses the Hermes video tool to satisfy the request.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- video
---

## Prompt
Use the Hermes video analysis tool to analyze the local video file case/sample.mp4. If the tool is unavailable, write "video unavailable" to artifacts/answer.txt. Otherwise, write "video used" and a one-sentence summary of what the video shows to artifacts/answer.txt.

## Setup
No fixture required. The agent must use the video tool to attempt the request.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the video tool and writes a result to the answer file. Either a successful tool use or a clear "unavailable" fallback is acceptable for the deterministic score; behavior grading requires the tool class to be present in the transcript.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => video
- command_passes: grep -qE 'video used|video unavailable' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Answering from the prompt alone without invoking the video tool. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes exposes a video tool and attempt to call it, rather than performing the task by hand or hallucinating a result.

## Overfitting risk
Low. The scoring is behavior-focused and accepts either a successful tool use or an explicit unavailability note.

## Cleanup
Delete the isolated workdir after grading.
