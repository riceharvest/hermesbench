---
id: htu-dev-015-messaging
title: Natural Tool-Use - Messaging
category: natural-tool-use
category_detail: messaging
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- messaging
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Prompt is stable. Target message and recipient are fixed.
safety_notes: Messaging tool only. No external side effects beyond the configured messaging provider.
human_baseline_minutes: 5
human_baseline_success_rate: 0.80
quality_tier: experimental
quality_notes: Tests whether the model uses the Hermes messaging tool to send a message to a recipient.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- messaging
---

## Prompt
Use the Hermes messaging features or send_message tool to send a message 'Hello from HermesBench' to recipient 'user-123'. If the messaging tool is unavailable, write 'messaging unavailable' to `artifacts/answer.txt`. Otherwise, write 'messaging sent' to `artifacts/answer.txt` and save a copy of the sent message details to `artifacts/sent.txt`.

## Setup
No fixture required. This task requires a configured messaging tool/provider.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the send_message tool and writes a result to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => messaging
- command_passes: test -s artifacts/sent.txt || grep -q 'messaging unavailable' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Writing a mock response without using the messaging tool. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes has a messaging tool and attempt to use it.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
