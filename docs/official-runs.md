# Official Runs

A HermesBench run is official only when a maintainer operates it, reviews it, and archives public-safe evidence under [`official-runs/`](../official-runs/). Local exploratory output in `results/` and `artifacts/` is ignored by Git. The legacy `official_runs/TEMPLATE.yaml` (underscore) remains at the old path as a manifest template; it is not an evidence archive. New evidence should use the `official-runs/` (hyphenated) directory.

## Capability scope

Official evidence must state whether it covers the portable **core CLI** surface or one or more optional **integrations**. Integrations such as browser automation, connected services, desktop control, and skills depend on runtime configuration, credentials, and local services. An unavailable integration is an environmental limitation to disclose, not a model failure. A mock-adapter run is deterministic plumbing evidence only and is never model-capability evidence.

## Who can run official submissions

Only designated maintainers may mark runs official. Self-submitted uploads are always unofficial, even when they use the public task suite.

## Required disclosure

Official manifests disclose hardware/runtime, OS, provider, model, agent version, runner commit, timeout policy, retry policy, suite version, capability scope (core CLI and named integrations), available toolsets, and result hash.

## Private packs (optional)

For sensitive or rotating fixture data, private packs must live outside the repository and set `HERMESBENCH_PRIVATE_PACK_DIR=/secure/path/to/tasks` before discovery/validation. The external directory uses the same `manifest.yaml` plus `suite/task.md` layout as `tasks/`; fixtures may be placed in a sibling `fixtures/` directory or bundled in the pack. Use `python scripts/private_pack.py --pack /secure/path/to/tasks` to sanity-check the pack without copying secrets into git.

## Archive requirements

Each official archive contains `result.json`, `manifest.yaml`, `score-summary.json`, and `SHA256SUMS`. Archives must not include submission tokens, private hidden-check material, or local secrets.

## Conflicts of interest

Operators disclose material conflicts in manifest notes. A second maintainer should review runs involving the operator's own agent/model.

## Unofficial labeling

Public API uploads are stored and displayed as unofficial. The public upload path rejects `metadata.official=true`. Historical mock data used by the website is labeled non-capability fixture data and is not a leaderboard result.

## Website data sources

The checked-in website source includes static sample data under the `website/` directory — these are **historical mock fixtures** for development and demo purposes only. They contain synthetic output from the `mock` adapter and do not represent real model capabilities or benchmark results.

Three pre-pivot result files remain tracked under `results/` (committed before `/results/` was added to `.gitignore`). They are legacy `mock`-adapter output and not model-capability evidence. New exploratory output is correctly ignored.

A separate live API leaderboard (hosted on Vercel or another platform) fetches submitted result data on demand. The static fixture files in this repository are never a substitute for the live leaderboard. Any description of "leaderboard" or "results" in the checked-in website frontend refers to proof-of-concept display logic; the authoritative result data lives outside this repository in the live API.
