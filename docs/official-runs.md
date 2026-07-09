# Official Runs

A HermesBench run is official only when a maintainer operates it and archives the raw result JSON plus environment metadata. Private/fresh packs are optional for most tool-use capability probes; official status depends on maintainer execution and manifest review, not on the upload endpoint.

## Who can run official submissions

Only designated maintainers may mark runs official. Self-submitted uploads are always unofficial, even when they use the public task suite.

## Required disclosure

Official manifests disclose hardware/runtime, OS, provider, model, agent version, runner commit, timeout policy, retry policy, suite version, and result hash.

## Private packs (optional)

For most tool-use capability probes, private packs are unnecessary because contamination is irrelevant: the probe tests whether the agent chooses the right tool class, not whether it memorizes a specific puzzle solution. If you do use a private pack for sensitive or rotating fixture data, it must live outside the repository and set `HERMESBENCH_PRIVATE_PACK_DIR=/secure/path/to/tasks` before discovery/validation. The external directory uses the same `manifest.yaml` plus `suite/task.md` layout as `tasks/`; fixtures may be placed in a sibling `fixtures/` directory or bundled in the pack. Use `python scripts/private_pack.py --pack /secure/path/to/tasks` to sanity-check the pack without copying secrets into git.

## Archive requirements

Each official archive contains `result.json`, `manifest.yaml`, `score-summary.json`, and `SHA256SUMS`. Archives must not include submission tokens or private hidden-check material.

## Conflicts of interest

Operators disclose material conflicts in manifest notes. A second maintainer should review runs involving the operator's own agent/model.

## Unofficial labeling

Public API uploads are stored and displayed as unofficial. The public upload path rejects `metadata.official=true`.
