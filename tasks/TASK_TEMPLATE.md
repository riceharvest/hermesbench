---
id: htu-dev-000-example
title: Natural Tool-Use - Example
category: natural-tool-use
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets:
- terminal
- file
grading_type: deterministic
tool_use_requirements:
- file
- terminal
timeout_seconds: 180
contamination_notes: Vague local-only task; no hidden oracle.
safety_notes: Credential-free local fixture.
---

## Prompt
Provide a brief prompt that forces the agent to autonomously decide to use the required tools (e.g. read_file, terminal, etc.) to achieve a specific goal. Do not instruct the model on which tool to use.

## Setup
Explain any local files or environment variables needed for this task.

## Expected artifacts
List files the agent should produce if any.

## Scoring rubric
The grader checks whether the agent invoked the required tool classes (as specified in `tool_use_requirements`) during the trajectory telemetry.

## Deterministic checks
- artifact_exists: artifacts/answer.txt

## Failure mode tested
Describe the specific tool-use capability being tested.

## Why hard for agents
Describe why a model might struggle (e.g. failing to choose the correct tool class or saying "done" prematurely).

## Overfitting risk
Describe overfitting risks.

## Cleanup
Instructions to clean up.
