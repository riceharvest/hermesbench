# Official Runs

A HermesBench run is official only when a maintainer operates it, reviews it, and archives public-safe evidence under [`official-runs/`](../official-runs/). Local exploratory output in `results/` and `artifacts/` is ignored by Git. The legacy `official_runs/TEMPLATE.yaml` (underscore) remains at the old path as a manifest template; it is not an evidence archive. New evidence should use the `official-runs/` (hyphenated) directory.

## Capability scope

Official evidence must state whether it covers the portable **core CLI** surface or one or more optional **integrations**. Integrations such as browser automation, connected services, desktop control, and skills depend on runtime configuration, credentials, and local services. An unavailable integration is an environmental limitation to disclose, not a model failure.

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

Public API uploads are stored and displayed as unofficial. The public upload path rejects `metadata.official=true` and `agent=mock`. No static mock data exists in the repository. Only reviewed, archived official runs appear as public capability evidence.
