# Official Runs

A HermesBench run is official only when a maintainer operates it against maintainer-controlled private/fresh task packs and archives the raw result JSON plus environment metadata.

## Who can run official submissions

Only designated maintainers may mark runs official. Self-submitted community uploads are always unofficial, even when they use the public task suite.

## Required disclosure

Official manifests disclose hardware/runtime, OS, provider, model, agent version, runner commit, timeout policy, retry policy, private pack ID, and result hash.

## Timeout and retry policy

Timeouts must use the benchmark task defaults unless a versioned policy states otherwise. Retries are permitted only for infrastructure failures and must be noted in the manifest.

## Cost tracking

Maintainers should capture provider invoices or run logs sufficient to estimate cost per successful task when available.

## Private task handling

Private packs are never published before official scoring windows close. Public `private-holdout` files are executable templates/sample holdouts with real fixtures, but official runs should point at an external pack with rotated values and hidden checks. Put that pack outside the repository and set `HERMESBENCH_PRIVATE_PACK_DIR=/secure/path/to/tasks` before discovery/validation. The external directory uses the same `manifest.yaml` plus `suite/task.md` layout as `tasks/`; fixtures may be placed in a sibling `fixtures/` directory or bundled in the pack. Use `python scripts/private_pack.py --pack /secure/path/to/tasks` to sanity-check the pack without copying secrets into git.

## Fresh rolling regeneration

Fresh public waves are generated with rotated fixtures via `python scripts/create_fresh_wave.py --wave fresh-YYYY-MM --count N --seed <operator-seed>`. Review generated values, commit only redistributable fresh fixtures, and record the wave id in the official manifest.

## Archive requirements

Each official archive contains `result.json`, `manifest.yaml`, `score-summary.json`, and `SHA256SUMS`. Archives must not include submission tokens or private hidden-check material.

## Conflicts of interest

Operators disclose material conflicts in manifest notes. A second maintainer should review runs involving the operator's own agent/model.

## Unofficial labeling

Public API uploads are stored and displayed as unofficial. The public upload path rejects `metadata.official=true`.
