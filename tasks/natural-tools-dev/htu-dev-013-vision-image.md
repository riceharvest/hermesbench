---
id: htu-dev-013-vision-image
title: Natural Tool-Use - Vision Image
category: natural-tool-use
category_detail: vision
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- vision
- file
fixtures:
- case/image.png
grading_type: deterministic
timeout_seconds: 180
contamination_notes: Static local fixture. Public prompt is stable; the image content is fixed.
safety_notes: Local image and vision tool only. No external side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.85
quality_notes: Tests whether the model uses the vision tool to interpret an image instead of writing OCR code.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- vision
---

## Prompt
The file `case/image.png` contains a digit. Use the Hermes vision tool to identify the digit and write it to `artifacts/answer.txt`.

## Setup
The runner copies the public fixture into the workdir.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the vision tool and writes the correct digit.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => 7
- command_contains: cat artifacts/answer.txt => 7

## Hidden checks
- No hidden checks.

## Failure mode tested
Writing Python OCR code instead of using the provided vision tool. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes has a vision tool and use it to interpret the image.

## Overfitting risk
Low. The scoring is behavior-focused and the fixture image is arbitrary.

## Cleanup
Delete the isolated workdir after grading.
