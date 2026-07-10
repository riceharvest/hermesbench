---
id: htu-dev-029-discord-admin
title: Natural Tool-Use - Discord Admin Required
category: natural-tool-use
category_detail: discord-admin
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-09
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- discord_admin
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Prompt is stable. The task tests whether the agent discovers the discord_admin tool.
safety_notes: Discord admin tool only. No external side effects beyond the configured provider.
human_baseline_minutes: 5
human_baseline_success_rate: 0.75
quality_tier: experimental
quality_notes: Tests whether the model uses the Hermes discord_admin tool to satisfy the request.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- discord_admin
---

## Prompt
Use the Hermes Discord Admin tool to search for a member by query "admin". If the tool is unavailable, write "discord_admin unavailable" to artifacts/answer.txt. Otherwise, write "discord_admin used" and the number of matched members to artifacts/answer.txt.

## Setup
No fixture required. The agent must use the discord_admin tool to attempt the request.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the discord_admin tool and writes a result to the answer file. Either a successful tool use or a clear "unavailable" fallback is acceptable for the deterministic score; behavior grading requires the tool class to be present in the transcript.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => discord_admin
- command_passes: grep -qE 'discord_admin used|discord_admin unavailable' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Answering from the prompt alone without invoking the discord_admin tool. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes exposes a separate discord_admin tool and attempt to call it, rather than performing the task by hand or hallucinating a result.

## Overfitting risk
Low. The scoring is behavior-focused and accepts either a successful tool use or an explicit unavailability note.

## Cleanup
Delete the isolated workdir after grading.
