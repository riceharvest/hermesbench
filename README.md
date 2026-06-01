# HermesBench

[![CI](https://github.com/hermesbench/hermesbench/actions/workflows/ci.yml/badge.svg)](https://github.com/hermesbench/hermesbench/actions) [![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE) ![Tasks](https://img.shields.io/badge/tasks-45-orange)

HermesBench is a real-world benchmark for Hermes-style tool-using agents. It tests whether agents can complete practical tasks with files, terminals, browsers, docs, logs, configs, schedules, email-like fixtures, code, and verification discipline.

Static LLM benchmarks are benchmaxxed: contaminated, overfit, and too far from messy agent work. HermesBench is different: execution-based scoring, public/dev plus private/fresh/anchor splits, hidden-check support, cost/latency/tool-call tracking, and explicit false-done penalties when an agent claims success without verified artifacts.

## Project status

HermesBench is public and CI-green, but official leaderboard runs are not launched yet. See `docs/PROCESS_STATUS.md` for the current stage tracker and gates.

## Quick start

```bash
uv run hermesbench validate-tasks
uv run hermesbench run --agent mock --suite public-dev --output-dir /tmp/hermesbench-results
uv run hermesbench score /tmp/hermesbench-results/*.json
```

Run one task or a real Hermes agent:

```bash
uv run hermesbench run --task hb-dev-001-sanity-basic-tool-use --agent mock
uv run hermesbench run --agent hermes --model openai-codex/gpt-5.5
```

## Task categories

The public/dev suite includes 30 tasks spanning sanity/tool use, file ops, codebase navigation, bugfixes, PR summaries, issue triage, docs research, provider config troubleshooting, browser automation, CSV/data analysis, logs, CVE triage, Dockerfile optimization, CI/CD diagnosis, cron, context recovery, memory boundaries, email/calendar fixtures, mock APIs, false-done traps, skills, K8s, spreadsheets, freshness-aware research, artifact audits, cost/latency analysis, tool planning, and hidden-check design. Additional suites include 5 private-holdout tasks, 5 fresh-rolling tasks, and 5 stable anchor tasks.

## Result schema

Results use `hermesbench.result.v1` with run metadata, per-task status, score, wall time, tool calls, optional cost, timeout, false-done flag, and verification evidence. `hermesbench score` emits `hermesbench.score.v1` aggregates: overall score, category scores, pass@1, cost per success, median wall time, tool-call count, verification compliance, false-done rate, and timeout rate.

## Add tasks

Copy `tasks/TASK_TEMPLATE.md`, add YAML metadata, prompt/setup/artifacts/rubric/checks/cleanup, add fixtures under `fixtures/<task-id>/`, update `tasks/manifest.yaml`, then run `uv run hermesbench validate-tasks`.

## Submit results

For now, publish the normalized result JSON. The upload/API contract is scaffolded in `docs/api.md`; official hidden/private runs are reserved for maintainers. See `docs/official-runs.md` for the official-run policy: community/API uploads are unofficial by default, and only maintainer-operated private/fresh-pack runs with archived manifests may be marked official.

## Reproducibility

Public/dev tasks require no external credentials. The runner creates isolated temp workdirs, seeds fixtures, enforces timeouts, and redacts hidden checks from public output. Private/fresh waves should be versioned and archived for audits.

## Provenance

This repo preserves the previous qwen-mtp-probe Hermes eval artifacts alongside HermesBench. See `docs/provenance.md`.

## Website and deployment

The static website lives in `website/` and builds with `cd website && pnpm install && pnpm build`. Deployment instructions are in `docs/deployment-website.md`.

## Release process

Benchmark releases use the checklist in `docs/release-process.md`; do not label a release as official until `docs/launch-readiness-v0.1.md` is satisfied.
