---
name: Task addition or capability probe
about: Propose or track a new HermesBench capability probe
title: "Probe: <tool-class>-NNN-short-name"
labels: [probe, benchmark]
assignees: []
---

## Probe ID
`<tool-class>-NNN-short-name`

## Target tool classes
List the Hermes tool/feature classes this probe exercises (e.g., `computer_use`, `clarify`, `cronjob`).

## Open-ended goal
Describe what the agent should accomplish without telling it which tool to use.

## Required capability evidence
- Telemetry signal that proves the correct tool class was invoked.
- Expected observable side effect or artifact, if any.

## Contamination review
- [ ] Prompt does not contain a hidden oracle or exact answer.
- [ ] Expected behavior tests tool-choice, not memorization.
- [ ] No private data, credentials, or embargoed material included.
- [ ] Public fixture values are redistributable.

## Checks
- [ ] At least one telemetry-based check for each required tool class.
- [ ] Deterministic artifact checks, if applicable.
- [ ] Timeout and false-done behavior considered.

## Closeout
- [ ] Probe added to `tasks/manifest.yaml`.
- [ ] `validate-tasks` passes.
- [ ] Mock or real adapter run passes locally.
