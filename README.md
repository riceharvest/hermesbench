# HermesBench

[![CI](https://github.com/riceharvest/hermesbench/actions/workflows/ci.yml/badge.svg)](https://github.com/riceharvest/hermesbench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Tasks](https://img.shields.io/badge/tasks-50-orange)
![Status](https://img.shields.io/badge/status-pre--official-blue)

HermesBench is an execution-based benchmark for Hermes-style tool-using agents: agents that read files, run commands, inspect fixtures, write artifacts, recover context, and verify work before claiming success.

Static LLM benchmarks are increasingly benchmaxxed: prompts leak, public answers get trained on, and leaderboard wins stop predicting whether an agent can actually finish messy work. HermesBench is designed around the opposite signal: did the agent produce the artifact, pass deterministic checks, avoid false-done behavior, and leave auditable evidence?

## What makes it different

- **Execution-first scoring:** deterministic, artifact, and test-based graders are preferred over vibes.
- **False-done penalties:** agents that say “done” without verified artifacts are measured, not rewarded.
- **Public/dev vs private/fresh/anchor splits:** public tasks are for development; official integrity requires maintainer-controlled private/fresh packs and stable anchors.
- **Tool-using agent focus:** tasks cover terminals, files, configs, logs, docs, data analysis, scheduling-like fixtures, browser-style workflows, and multi-step local APIs.
- **Normalized run JSON:** scores include pass@1, category scores, wall time, tool calls, timeouts, cost when available, and verification evidence.
- **Adapter architecture:** the runner supports a mock adapter, Hermes CLI adapter, and generic shell adapter; Codex/Claude/OpenCode-style shell presets can be added without changing task format.

## Current status

HermesBench is public, CI-green, and usable locally. It is **not yet an official leaderboard**. Official scores require real private task packs outside this public repository plus archived maintainer-run manifests. See [`docs/PROCESS_STATUS.md`](docs/PROCESS_STATUS.md), [`docs/official-runs.md`](docs/official-runs.md), and [`docs/launch-readiness-v0.1.md`](docs/launch-readiness-v0.1.md).

## Quick start

```bash
git clone https://github.com/riceharvest/hermesbench.git
cd hermesbench
uv run hermesbench validate-tasks
uv run hermesbench run --agent mock --suite public-dev --output-dir /tmp/hermesbench-results
uv run hermesbench score /tmp/hermesbench-results/*.json
```

The default install is intentionally lightweight. ML/model-probing dependencies are optional and are not needed for HermesBench task validation, mock runs, scoring, or the public CLI:

```bash
uv sync --dev                    # development/test tools
uv sync --extra ml               # legacy Qwen/model-probing research tools only
```

Run one task:

```bash
uv run hermesbench run --agent mock --task hb-dev-001-sanity-basic-tool-use --output-dir /tmp/hermesbench-one
uv run hermesbench score /tmp/hermesbench-one/*.json
```

Run with Hermes CLI when you have Hermes configured:

```bash
uv run hermesbench run --agent hermes --model openai-codex/gpt-5.5 --suite public-dev --output-dir results/hermes-public-dev
```

## CLI reference

```bash
uv run hermesbench validate-tasks
uv run hermesbench versions
uv run hermesbench run --agent mock --suite public-dev
uv run hermesbench run --agent hermes --provider openai-codex --model gpt-5.5 --reasoning-effort low
uv run hermesbench run --agent mock --benchmark-version hermesbench-v0.1
uv run hermesbench run --agent shell --command './my-agent-runner.sh'
uv run hermesbench score results/<run>.json
uv run hermesbench export --format jsonl
uv run hermesbench upload results/<run>.json
uv run hermesbench serve-api --host 127.0.0.1 --port 8787
uv run hermesbench archive-official --result results/run.json --manifest official_runs/run.yaml --output official_runs/archive/run
```

## Repository layout

See [`REPOSITORY_MAP.md`](REPOSITORY_MAP.md) for a more explicit identity/provenance map.

```text
src/hermesbench/          Python CLI, runner, schemas, adapters, graders, API/storage
src/hermesbench/adapters/ mock, Hermes CLI, and shell adapter implementations
src/hermesbench/graders/  deterministic artifact/test checks
src/qwen_mtp_probe/       legacy research/provenance namespace; not packaged as HermesBench
tasks/                    benchmark task markdown and manifest
tasks/public-dev/         public development suite
tasks/anchor/             stable anchor templates/tasks
tasks/fresh-rolling/      fresh-wave templates/tasks
tasks/private-holdout/    public templates only; real private pack stays private
fixtures/                 local deterministic task fixtures
benchmark_versions/       benchmark version registry
docs/                     methodology, governance, deployment, release docs
website/                  static leaderboard/landing site scaffold
tests/                    parser, runner, API, storage, official-run, and website-adjacent tests
```

## Task suites

| Suite | Count | Purpose | Credential-free |
|---|---:|---|---|
| `public-dev` | 35 | Public local development and regression suite | Yes |
| `anchor` | 5 | Stable longitudinal comparison templates/tasks | Yes |
| `fresh-rolling` | 5 | Fresh-wave workflow starters | Yes |
| `private-holdout` | 5 | Public templates for private holdout shape; not official hidden tasks | Yes |

The manifest currently contains 70 entries total: 55 public-dev tasks, 5 public anchor tasks, 5 public fresh-rolling starter tasks, and 5 public private-holdout sample/template tasks. The committed private-holdout files are executable samples; real official private packs stay outside the public repo and are loaded separately for maintainer runs.

Public/dev categories include sanity/tool use, file operations, codebase navigation, bugfixes with tests, PR summaries, GitHub issue triage, docs research, provider config troubleshooting, browser automation, CSV/data analysis, log analysis, CVE triage, Dockerfile optimization, CI/CD diagnosis, cron scheduling, session/context recovery, memory/profile boundaries, email/calendar-style fixtures, mock APIs, false-done traps, skills, K8s debugging, spreadsheets, freshness-aware research, artifact audit, cost/latency analysis, tool-call planning, hidden-check design, and common-use-case domains such as marketing, SEO, technology vendor evaluation, science claim checking, translation, legal risk spotting, finance forecasting, health triage, trivia fact-checking, and academia citation auditing.

## Task format

Tasks are Markdown files with YAML frontmatter and structured sections:

```yaml
id: hb-dev-001-sanity-basic-tool-use
title: Sanity/basic tool use
category: sanity-basic-tool-use
wave: public-dev-2026-06
visibility: public
created_at: 2026-06-01
freshness_window: stable-anchor
expected_human_minutes: 6
difficulty: medium
required_toolsets: [terminal, file]
grading_type: deterministic
timeout_seconds: 120
contamination_notes: Public dev task; private waves vary fixture values.
safety_notes: Local fixtures only; no credentials.
```

Sections include prompt, setup, expected artifacts, scoring rubric, deterministic checks, hidden-check notes, and cleanup instructions. Start from [`tasks/TASK_TEMPLATE.md`](tasks/TASK_TEMPLATE.md).

## Result schema and scoring

Runner output uses `hermesbench.result.v1`. Scoring emits `hermesbench.score.v1` with:

- provider, model, and reasoning effort (`none|minimal|low|medium|high|xhigh`) because reasoning depth materially changes cost/latency/quality
- overall score
- category scores
- pass@1
- cost per successful task when telemetry exists
- median wall time
- tool-call count
- verification compliance
- false-done rate
- timeout rate
- raw per-task evidence for audits

Example:

```bash
uv run hermesbench score /tmp/hermesbench-results/*.json
```

## Submissions and API

The current API scaffold supports local/testable submissions:

- `POST /v1/results`
- `GET /v1/leaderboard`
- `GET /health`

Public uploads are unofficial by default. `metadata.official=true` is maintainer-reserved and rejected by public upload validation. Submission tokens are stripped before persistence. See [`docs/api.md`](docs/api.md) and [`docs/deployment-api.md`](docs/deployment-api.md).

## Website

Live site: **https://hermesbench.site**

The static website lives in [`website/`](website/) and is deployable to GitHub Pages, Vercel, or any static host:

```bash
cd website
pnpm install
pnpm build
```

The site includes a landing page, methodology overview, task-suite explanation, demo leaderboard, result detail panel, and submission guidance. Deployment notes are in [`docs/deployment-website.md`](docs/deployment-website.md).

## Adding tasks

1. Copy [`tasks/TASK_TEMPLATE.md`](tasks/TASK_TEMPLATE.md).
2. Add fixture files under `fixtures/<task-id>/` unless `no_fixture_required: true` is justified.
3. Document `Failure mode tested`, `Why hard for agents`, and `Overfitting risk` (see [`docs/task-format.md`](docs/task-format.md)).
4. Use at least four substantive deterministic checks whenever possible, including command and semantic validation rather than marker-only files.
5. Add hidden-check notes for future private/fresh variants.
6. Update `tasks/manifest.yaml`.
7. Run:

```bash
uv run hermesbench validate-tasks
uv run pytest tests/test_hermesbench_core.py -q
```

## Reproducibility and benchmark integrity

- Public/dev tasks require no external credentials.
- Each task runs in an isolated temp workdir.
- Fixtures are copied per task.
- Hidden checks are not emitted in public output.
- Official runs require maintainer-controlled private/fresh packs, run manifests, hashes, and archived score evidence.
- Do not compare unofficial public/dev self-runs to official private/fresh/anchor leaderboard runs.

## Development checks

```bash
uv run pytest
uv run hermesbench validate-tasks
rm -rf /tmp/hermesbench-results
uv run hermesbench run --agent mock --suite public-dev --output-dir /tmp/hermesbench-results
uv run hermesbench score /tmp/hermesbench-results/*.json
cd website && pnpm install && pnpm build
```

## Provenance

This repository started from the `qwen-mtp-probe` working repo and preserves older Hermes eval artifacts for auditability. See [`docs/provenance.md`](docs/provenance.md). The shipped Python package is `hermesbench` from `src/hermesbench/`; legacy model-specialization files in `src/qwen_mtp_probe/` remain source-tree research/provenance material and are not included in the HermesBench wheel.

## License

MIT. See [`LICENSE`](LICENSE).
