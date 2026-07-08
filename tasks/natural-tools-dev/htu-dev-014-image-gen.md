---
id: htu-dev-014-image-gen
title: Natural Tool-Use - Image Generation
category: natural-tool-use
category_detail: image_gen
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: medium
required_toolsets:
- image_gen
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Static local fixture. Public prompt is stable; the generated image depends on the configured image generation provider.
safety_notes: Image generation tool only. No external side effects beyond the configured image provider.
human_baseline_minutes: 5
human_baseline_success_rate: 0.75
quality_tier: experimental
quality_notes: Tests whether the model uses the Hermes image generation tool to create an image. Requires a configured image generation provider.
requires_skills: false
coding_required: false
external_web: false
tool_use_requirements:
- image_gen
---

## Prompt
Use the Hermes image_gen tool to generate an image of a red circle and save it to `artifacts/image.png`. Then write the name of the tool you used (or "image_gen unavailable") to `artifacts/answer.txt`.

## Setup
No fixture required. This task requires a configured image generation provider.

## Expected artifacts
- artifacts/answer.txt
- artifacts/image.png (when the image generation provider is available)

## Scoring rubric
Pass if the agent uses the image_gen tool and writes a result to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- artifact_contains: artifacts/answer.txt => image_gen
- command_passes: test -s artifacts/image.png || grep -q 'image_gen unavailable' artifacts/answer.txt

## Hidden checks
- No hidden checks.

## Failure mode tested
Writing a placeholder image without using the image generation tool. The task specifically tests feature discovery.

## Why hard for agents
The model must know that Hermes has an image generation tool and attempt to use it.

## Overfitting risk
Low. The scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
