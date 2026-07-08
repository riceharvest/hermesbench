---
id: htu-dev-011-cronjob-schedule
title: Natural Tool-Use - Schedule a Cronjob
category: natural-tool-use
category_detail: cronjob
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- cronjob
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Public prompt is stable; the job content is fixed.
safety_notes: Cronjob tool only. No external side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.75
quality_tier: experimental
quality_notes: Tests whether the model schedules and runs a job using the Hermes cronjob tool. Requires a working Hermes cron scheduler.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- cronjob
---

## Prompt
Use the Hermes cronjob tool to schedule a one-off job that writes "cron done" to `artifacts/answer.txt`. Then immediately run the job using the cronjob tool with action='run'. If the tool is unavailable, write "cron unavailable" to `artifacts/answer.txt`.

## Setup
No fixture required. The agent must use the cronjob tool to schedule and run the job.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the cronjob tool and writes a result to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => cron
- command_passes: grep -qE 'cron done|cron unavailable' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Writing the file directly instead of using the cronjob tool. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes has a cronjob tool, schedule a job, and run it.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
