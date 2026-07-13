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
quality_notes: Tests whether the model schedules a job using the Hermes cronjob tool without depending on an asynchronous scheduler daemon.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- cronjob
---

## Prompt
Use the Hermes cronjob tool to schedule a one-off **agent-driven** job (do not use the `script` parameter) whose prompt is `cron benchmark marker`. Use a short future schedule such as `1m`. After the cronjob create call succeeds and returns a `job_id`, use `write_file` in this parent session to write exactly `cron done` followed by a newline to `artifacts/answer.txt` as deterministic proof that you completed the scheduling step. Do not call `action='run'`: one-shot benchmark sessions do not run the asynchronous scheduler loop. Do not create a shell script.

Do not write the artifact unless the cronjob create call succeeded. Do not claim completion until the artifact exists with the expected text. The final response alone is not sufficient.

## Setup
No fixture required. The agent must use the cronjob tool to schedule the job.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent successfully uses the cronjob tool and writes the marker to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => cron done
- command_passes: grep -qE '^cron done$' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Writing the file without first creating a cronjob. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes has a cronjob tool, schedule an agent-driven job, and verify its parent-side artifact. The prompt avoids asynchronous scheduler execution and the separate profile-script path contract, neither of which is part of this task's capability target.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
