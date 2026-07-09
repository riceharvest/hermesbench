# HermesBench

[![CI](https://github.com/riceharvest/hermesbench/actions/workflows/ci.yml/badge.svg)](https://github.com/riceharvest/hermesbench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Tasks](https://img.shields.io/badge/tasks-15-orange)
![Status](https://img.shields.io/badge/status-pre--official-blue)

HermesBench is a **minimum-capable-model probe** for Hermes-style tool-using agents. It is designed to answer a specific question: *what is the lowest total-parameter model that can still use every tool and feature Hermes Agent exposes?* It is not a leaderboard of the best model for a fixed task; it is a search for the **worst model that is still good enough** — especially useful for local-AI deployment.

Existing benchmarks are increasingly benchmaxxed: prompts leak, public answers get trained on, and leaderboard wins stop predicting whether an agent can actually finish messy work. HermesBench flips the signal. We grade agentic behavior from telemetry, not output correctness. A task is a capability probe, not a puzzle with a known answer. The benchmark is open-ended by design: a model must autonomously decide which Hermes tool, skill, or workflow to invoke, and then actually do it. Failures are not "wrong answers"; they are missing capabilities.

## What makes it different

- **Capability-first scoring:** tasks are scored on whether the agent used the required Hermes tool or feature class from transcript telemetry, not on whether the final artifact looks right.
- **Minimum-capable-model goal:** the benchmark is optimized to find the smallest model (in total parameters) that can still drive every tool Hermes Agent needs.
- **Tool-class coverage:** probes every built-in tool category: `file`, `terminal`, `web`, `browser`, `code_execution`, `vision`, `image_gen`, `memory`, `todo`, `skills`, `session_search`, `delegation`, `clarify`, `cronjob`, `computer_use`, and `messaging`.
- **Open-ended prompts:** tasks do not specify which tool to use. The agent must choose, execute, and leave auditable evidence.
- **False-done penalties:** agents that say “done” without verified capability usage are measured, not rewarded.
- **Telemetry-based behavior grading:** evaluates real tool usage directly from execution telemetry instead of simple output matching.
- **Normalized run JSON:** scores include pass@1, tool-class coverage, wall time, tool calls, timeouts, cost when available, and verification evidence.
- **Adapter architecture:** the runner supports a mock adapter, Hermes CLI adapter, and generic shell adapter; any Hermes-compatible model can be evaluated without changing task format.

## Current status

HermesBench is public, CI-green, and usable locally. It functions as a local probe to assess tool coverage. See [`docs/official-runs.md`](docs/official-runs.md) and [`docs/methodology.md`](docs/methodology.md).

## Quick start

```bash
git clone https://github.com/riceharvest/hermesbench.git
cd hermesbench
uv run hermesbench validate-tasks
uv run hermesbench run --agent mock --suite natural-tools-dev --output-dir /tmp/hermesbench-results
uv run hermesbench score /tmp/hermesbench-results/*.json
```

The default install is intentionally lightweight:

```bash
uv sync --dev                    # development/test tools
```

Run one task:

```bash
uv run hermesbench run --agent mock --task htu-dev-001-file-and-terminal-self-serve --output-dir /tmp/hermesbench-one
uv run hermesbench score /tmp/hermesbench-one/*.json
```

Run with Hermes CLI against a local model to probe tool-class coverage:

```bash
uv run hermesbench run --agent hermes --model openai-codex/gpt-5.5 --suite natural-tools-dev --output-dir results/hermes-natural-tools-dev
```

## CLI reference

```bash
uv run hermesbench validate-tasks
uv run hermesbench versions
uv run hermesbench run --agent mock --suite natural-tools-dev --jobs auto
uv run hermesbench run --agent hermes --provider openai-codex --model gpt-5.5 --reasoning-effort low --suite natural-tools-dev --jobs auto
uv run hermesbench run --agent mock --benchmark-version hermesbench-v0.1 --jobs 1
uv run hermesbench run --agent shell --command './my-agent-runner.sh' --suite natural-tools-dev --jobs 4
uv run hermesbench score results/<run>.json
uv run hermesbench export --suite natural-tools-dev --format jsonl
uv run hermesbench upload results/<run>.json --endpoint https://hermesbench.site/v1/results
uv run hermesbench serve-api --host 127.0.0.1 --port 8787
uv run hermesbench archive-official --result results/run.json --manifest official_runs/run.yaml --output official_runs/archive/run
```

## Repository layout

See [`REPOSITORY_MAP.md`](REPOSITORY_MAP.md) for a more explicit identity/provenance map.

```text
src/hermesbench/          Python CLI, runner, schemas, adapters, graders, API/storage
src/hermesbench/adapters/ mock, Hermes CLI, and shell adapter implementations
src/hermesbench/graders/  deterministic artifact/test checks and telemetry-based behavior grading
tasks/                    benchmark task markdown and manifest
tasks/natural-tools-dev/  natural tool-use capability probes
fixtures/                 local deterministic task fixtures
docs/                     methodology, governance, deployment, release docs
website/                  leaderboard site with authenticated submissions
tests/                    parser, runner, API, storage, official-run, and website-adjacent tests
```

## Task suites

| Suite | Count | Purpose | Credential-free |
|---|---:|---|---|
|| `natural-tools-dev` | 15 | Open-ended capability probes for file, terminal, web, browser, code execution, vision, image generation, memory, todo, skills, session search, delegation, clarification, cron, computer use, and messaging | Some |

The `natural-tools-dev` suite is the primary suite for the minimum-capable-model probe. It contains 15 public tasks, each targeting one or more Hermes tool classes. Tasks are intentionally open-ended: they do not tell the model which tool to use, only the goal. Scoring inspects the transcript for the required Hermes tool class. A model that cannot choose and invoke the right tool class fails the capability probe, regardless of how plausible its final answer is.

| Task | Required tool classes | Difficulty | Notes |
|---|---|---:|---|
| `htu-dev-001` | `file`, `terminal` | easy | self-serve local data processing |
| `htu-dev-002` | `web` | easy | fetch a public web fact |
| `htu-dev-003` | `skills` | easy | use a skill to complete a task |
| `htu-dev-004` | `memory` | easy | recall a stored value |
| `htu-dev-005` | `delegation` | medium | parallelize subtasks via delegation |
| `htu-dev-006` | `todo`, `file` | easy | plan work with the todo tool |
| `htu-dev-007` | `code_execution` | easy | run code to compute an answer |
| `htu-dev-008` | `browser` | easy | navigate a site to extract a live fact |
| `htu-dev-009` | `session_search` | easy | search conversation history |
| `htu-dev-010` | `clarify` | medium | resolve an ambiguous request by asking |
| `htu-dev-011` | `cronjob` | medium | schedule a future job |
| `htu-dev-012` | `computer_use` | medium | interact with the desktop environment |
| `htu-dev-013` | `vision` | medium | read a value from an image |
| `htu-dev-014` | `image_gen` | medium | generate an image matching constraints |
| `htu-dev-015` | `messaging` | medium | message a user to report status |

Experimental tasks (browser, clarify, cronjob, computer_use, image_gen) require the corresponding Hermes toolset to be enabled and may depend on external credentials or a desktop environment.

## Task format

Tasks are Markdown files with YAML frontmatter and structured sections:

```yaml
id: htu-dev-001-file-and-terminal-self-serve
title: Natural Tool-Use - File + Terminal Self-Serve
category: natural-tool-use
wave: natural-tools-v0-2026-07
visibility: public
created_at: 2026-07-08
freshness_window: static
expected_human_minutes: 5
difficulty: easy
required_toolsets: [terminal, file]
grading_type: deterministic
tool_use_requirements: [file, terminal]
timeout_seconds: 180
contamination_notes: Vague local-only task; no hidden oracle.
safety_notes: Credential-free local fixture.
```

Sections include prompt, setup, expected artifacts, capability rubric, deterministic checks, hidden-check notes, and cleanup instructions. Start from [`tasks/TASK_TEMPLATE.md`](tasks/TASK_TEMPLATE.md).

## Result schema and scoring

Runner output uses `hermesbench.result.v1`. Scoring emits `hermesbench.score.v1` with:

- provider, model, and reasoning effort (`none|minimal|low|medium|high|xhigh`) because reasoning depth materially changes cost/latency/quality
- overall score
- **tool-class coverage**: which Hermes tool/feature classes were actually invoked by the agent
- **minimum-capable-model boundary**: the smallest reported model size that still satisfies every required tool class
- pass@1
- cost per successful task when telemetry exists
- median wall time
- tool-call count
- false-done rate
- timeout rate
- raw per-task evidence for audits

The primary result is not a ranking of the best model; it is a **minimum-parameter boundary**. The benchmark reports the smallest model that still satisfies every `tool_use_requirements` entry. A model that is smaller but misses a required capability is the answer we are looking for, because it tells users exactly what does *not* work for local deployment.

Example:

```bash
uv run hermesbench score /tmp/hermesbench-results/*.json
```

## Submissions and API

The current API scaffold supports one submission lane:

- `POST /v1/results` and `GET /v1/leaderboard` for authenticated submissions.
- `GET /health`

Uploaded runs are unofficial until maintainers promote them. `metadata.official=true` is maintainer-reserved and rejected by public upload validation. Submission tokens are stripped before persistence. See [`docs/api.md`](docs/api.md) and [`docs/deployment-api.md`](docs/deployment-api.md).

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
4. For capability tasks, declare the required Hermes tool/feature classes in `tool_use_requirements` and keep the prompt open-ended so the model must choose the tool.
5. Use at least four substantive deterministic checks whenever possible, including command and semantic validation rather than marker-only files.
6. Add hidden-check notes for future private/fresh variants.
6. Update `tasks/manifest.yaml`.
7. Run:

```bash
uv run hermesbench validate-tasks
uv run pytest tests/test_hermesbench_core.py -q
```

## Reproducibility and benchmark integrity

- Capability tasks may require credentials (web search, browser, external APIs) and are marked accordingly.
- Public natural-tool-use tasks require no external credentials unless noted.
- Each task runs in an isolated temp workdir.
- Fixtures are copied per task.
- Hidden checks are not emitted in public output.
- Trajectory telemetry is retained locally to audit tool invocation evidence.

## Development checks

```bash
uv run pytest
uv run hermesbench validate-tasks
rm -rf /tmp/hermesbench-results
uv run hermesbench run --agent mock --suite natural-tools-dev --output-dir /tmp/hermesbench-results
uv run hermesbench score /tmp/hermesbench-results/*.json
cd website && pnpm install && pnpm build
```

## License

MIT. See [`LICENSE`](LICENSE).
