# HermesBench

[![CI](https://github.com/riceharvest/hermesbench/actions/workflows/ci.yml/badge.svg)](https://github.com/riceharvest/hermesbench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
![Tasks](https://img.shields.io/badge/tasks-38-orange)
![Status](https://img.shields.io/badge/status-reviewed--evidence-blue)

HermesBench is a **tool-use benchmark harness** for Hermes-style agents. It reports two scopes: **`hermes-core`**, the tools and features shipped in the base Hermes Agent installation, and **`hermes-extended`**, the installable/configurable ecosystem tools and integrations. It does not claim a minimum-capable-model boundary for the full Hermes Agent surface; any boundary is specific to the archived suite, runner revision, and disclosed environment.

Existing benchmarks are increasingly benchmaxxed: prompts leak, public answers get trained on, and leaderboard wins stop predicting whether an agent can actually finish messy work. HermesBench flips the signal. We grade required tool trajectories from telemetry and task outcomes with deterministic checks, reporting those dimensions separately. A task is a capability probe, not just a puzzle with a known answer. The benchmark is open-ended by design: a model must autonomously decide which Hermes tool, skill, or workflow to invoke, and then actually do it.

## What makes it different

- **Scoped capability evidence:** core probes cover shipped Hermes features; extended probes are evidence only when the matching toolset, credentials, and service are available and disclosed.
- **Future minimum-capable-model goal:** once official, reproducible coverage exists, the data can be used to estimate the smallest model that satisfies a stated capability scope.
- **Tool-class coverage:** probes every built-in tool category: `file`, `terminal`, `web`, `browser`, `browser_cdp`, `code_execution`, `vision`, `image_gen`, `video`, `video_gen`, `tts`, `memory`, `todo`, `skills`, `session_search`, `semantic_search`, `delegation`, `clarify`, `cronjob`, `computer_use`, `homeassistant`, `kanban`, `project`, `discord`, `discord_admin`, `x_search`, `yuanbao`, `spotify`, `feishu`, `messaging`, `stt`, `obsidian`, `github`, `docker`, `notion`, `linear`, `maps`, `himalaya`, and `openhue`.
- **Auditable prompts:** tasks state a goal and required evidence; the agent must execute tools and leave verifiable artifacts. Some development probes explicitly name the target capability and are not yet autonomous-selection evaluations.
- **False-done penalties:** agents that say “done” without verified capability usage are measured, not rewarded.
- **Telemetry-based behavior grading:** evaluates real tool usage directly from execution telemetry instead of simple output matching.
- **Normalized run JSON:** scores include pass@1, tool-class coverage, wall time, tool calls, timeouts, cost when available, and verification evidence.
- **Adapter architecture:** the runner supports a Hermes CLI adapter for configured core-CLI/integration environments and a generic shell adapter. Adapter availability is not a claim that every Hermes integration is available or benchmarked.

## Current status

Hermes runs are preflighted against the toolsets the active runtime exposes. `hermes-core` and `hermes-extended` are reported separately; unavailable tools are environmental skips, not model failures. Results separate deterministic correctness (`task_correctness_pass`), required-tool evidence (`tool_capability_pass`), trusted runtime warnings, and cost-telemetry availability. Legacy `capability_pass` remains the strict combined gate. Score-per-dollar claims require `cost_telemetry_status=complete`; `complete_zero` is not proof of free inference. Only reviewed, hash-verified archives from a clean committed checkout appear as public capability evidence. See [`docs/official-runs.md`](docs/official-runs.md) and [`docs/methodology.md`](docs/methodology.md).

## Quick start

```bash
git clone https://github.com/riceharvest/hermesbench.git
cd hermesbench
uv run hermesbench validate-tasks
uv run hermesbench run --agent hermes --provider openai-codex --model gpt-5.5 --suite hermes-core --output-dir /tmp/hermesbench-results
uv run hermesbench score /tmp/hermesbench-results/*.json
```

The default install is intentionally lightweight:

```bash
uv sync --dev                    # development/test tools
```

Run one task with Hermes CLI to probe tool-class coverage:

```bash
uv run hermesbench run --agent hermes --model openai-codex/gpt-5.5 --suite hermes-core --output-dir results/hermes-core
# Run installable/configurable tools only in an environment that exposes and documents them:
uv run hermesbench run --agent hermes --model openai-codex/gpt-5.5 --suite hermes-extended --output-dir results/hermes-extended
```

## CLI reference

```bash
uv run hermesbench validate-tasks
uv run hermesbench versions
uv run hermesbench run --agent hermes --provider openai-codex --model gpt-5.5 --reasoning-effort low --suite hermes-core --jobs auto
uv run hermesbench run --agent hermes --benchmark-version hermes-core-v0.1 --jobs 1
uv run hermesbench run --agent shell --command './my-agent-runner.sh' --suite hermes-core --jobs 4
uv run hermesbench score results/<run>.json
uv run hermesbench export --suite hermes-core --format jsonl
uv run hermesbench upload results/<run>.json --endpoint https://www.benchcut.info/v1/results
uv run hermesbench serve-api --host 127.0.0.1 --port 8787
uv run hermesbench archive-official --result results/run.json --manifest official-runs/run.yaml --output official-runs/archive/run
```

## Repository layout

See [`REPOSITORY_MAP.md`](REPOSITORY_MAP.md) for a more explicit identity/provenance map.

```text
src/hermesbench/          Python CLI, runner, schemas, adapters, graders, API/storage
src/hermesbench/adapters/ Hermes CLI and shell adapter implementations
src/hermesbench/graders/  deterministic artifact/test checks and telemetry-based behavior grading
tasks/                    benchmark task markdown and manifest
tasks/natural-tools-dev/  38 probes partitioned into hermes-core/hermes-extended
fixtures/                 local deterministic task fixtures
docs/                     methodology, governance, deployment, release docs
website/                  leaderboard site with authenticated submissions
tests/                    parser, runner, API, storage, official-run, and website-adjacent tests
```

## Task suites

| Suite | Count | Purpose | Credential-free |
|---|---:|---|---|
| `hermes-core` | 13 | Hermes tools and features shipped in the base installation | Varies |
| `hermes-extended` | 25 | Installable/configurable tools and integrations | No |

`hermes-core` and `hermes-extended` are separate reporting scopes. Run and publish them separately: core results do not imply every optional integration is configured, and unavailable extended tools are environmental skips, not model failures.

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
| `htu-dev-016` | `x_search` | medium | search X for a recent post |
| `htu-dev-017` | `video` | medium | analyze a local video file |
| `htu-dev-018` | `video_gen` | medium | generate a short video |
| `htu-dev-019` | `tts` | medium | convert text to speech |
| `htu-dev-020` | `homeassistant` | medium | list Home Assistant entities |
| `htu-dev-021` | `discord` | medium | list Discord channels |
| `htu-dev-022` | `browser_cdp` | medium | inspect a page via browser CDP |
| `htu-dev-023` | `kanban` | medium | list Kanban tasks |
| `htu-dev-024` | `project` | medium | list available projects |
| `htu-dev-025` | `semantic_search` | medium | find files by semantic search |
| `htu-dev-026` | `feishu` | medium | read a Feishu document |
| `htu-dev-027` | `yuanbao` | medium | query a Yuanbao group |
| `htu-dev-028` | `spotify` | medium | search Spotify for a track |
| `htu-dev-029` | `discord_admin` | medium | inspect Discord administration capabilities |
| `htu-dev-030` | `stt` | medium | transcribe an audio sample |
| `htu-dev-031` | `obsidian` | medium | read a vault note |
| `htu-dev-032` | `github` | medium | inspect GitHub workflow state |
| `htu-dev-033` | `docker` | medium | inspect Docker runtime state |
| `htu-dev-034` | `notion` | medium | read a Notion page |
| `htu-dev-035` | `linear` | medium | search Linear issues |
| `htu-dev-036` | `maps` | medium | geocode a location |
| `htu-dev-037` | `himalaya` | medium | list email folders |
| `htu-dev-038` | `openhue` | medium | inspect Hue lights |

Experimental tasks (browser, browser_cdp, clarify, cronjob, computer_use, image_gen, video, video_gen, tts, homeassistant, discord, discord_admin, kanban, project, semantic_search, feishu, yuanbao, spotify, x_search, messaging, stt, obsidian, github, docker, notion, linear, maps, himalaya, openhue) require the corresponding Hermes toolset to be enabled and may depend on credentials, local services, or a desktop environment.

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

## Hermes profiles and model selection

HermesBench runs use the isolated `hermesbench` profile by default. Create it once by cloning the active Hermes configuration:

```bash
hermes profile create hermesbench --clone --no-alias
```

Edit `~/.hermes/profiles/hermesbench/config.yaml` to choose the profile's normal local or cloud provider/model. A run may override those selections without changing the profile:

```bash
# Inherit provider/model from hermesbench
uv run hermesbench run --agent hermes --task htu-dev-001-file-and-terminal-self-serve

# Override for one local or cloud run
uv run hermesbench run --agent hermes --provider qwen --model Qwen3.6-35B-A3B-UD-Q3_K_M.gguf --task htu-dev-001-file-and-terminal-self-serve
```

Use `--profile PROFILE` to select another explicitly configured Hermes profile. Each task receives a temporary copy with its own working directory; sessions, memories, state databases, logs, and caches from the source profile are not copied, and the source profile is never modified. The selected profile is recorded in result metadata.

The GitHub real-agent checks run on the project's self-hosted Hermes runner and use the local `hermesbench` profile directly. Provider selection and credentials therefore remain local to Hermes; no provider credentials are copied into GitHub Actions. The runner must have the profile configured before a workflow is triggered.

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

Live site: **https://www.benchcut.info**

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
cd website && pnpm install && pnpm build
```

## License

MIT. See [`LICENSE`](LICENSE).
