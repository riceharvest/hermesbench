---
id: htu-dev-008-browser-required
title: Natural Tool-Use - Browser Required
category: natural-tool-use
category_detail: browser
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: rolling
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- browser_cdp
- file
no_fixture_required: true
grading_type: deterministic
timeout_seconds: 240
contamination_notes: Open-ended fact that changes over time and is not in the fixture. Public prompt is stable but the correct answer changes, so contamination is limited.
safety_notes: Browser automation only. No credentials or side effects.
human_baseline_minutes: 5
human_baseline_success_rate: 0.80
quality_notes: Tests whether the model uses browser automation instead of web search or hallucination for a current external fact.
requires_skills: false
coding_required: false
external_web: true
tool_use_requirements:
- browser
---

## Prompt
What is the current version of the latest stable release of the Hermes Agent framework? Use the browser tool to navigate to `https://hermes-agent.nousresearch.com/docs`, then follow the visible **Download** link and read the Hermes Agent version from the destination page footer. Write only that version string to `artifacts/answer.txt`. Do not use web search, browser console, or documentation search; only the browser automation tool is enabled and the Download link is the intended route.

## Setup
No fixture required. The agent must use the browser tool to discover the current version.

## Expected artifacts
- artifacts/answer.txt

## Scoring rubric
Pass if the agent uses the browser tool and writes a plausible version string to the answer file.

## Deterministic checks
- artifact_exists: artifacts/answer.txt
- command_passes: test -s artifacts/answer.txt
- command_passes: grep -qE 'v?[0-9]+\.[0-9]+' artifacts/answer.txt
- artifact_matches: artifacts/answer.txt => \d+\.\d+

## Hidden checks
- No hidden checks.

## Failure mode tested
Hallucinating a version or using web search when the task explicitly requires browser navigation.

## Why hard for agents
The prompt asks for a current external fact and specifies a particular tool class, testing whether the model respects tool constraints. The navigation route is explicit so the task measures browser use rather than open-ended documentation search.

## Overfitting risk
Low. The version string changes and the scoring is behavior-focused.

## Cleanup
Delete the isolated workdir after grading.
