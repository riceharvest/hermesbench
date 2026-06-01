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

Private packs are never published before official scoring windows close. Public `private-holdout` files are templates only.

## Archive requirements

Each official archive contains `result.json`, `manifest.yaml`, `score-summary.json`, and `SHA256SUMS`. Archives must not include submission tokens or private hidden-check material.

## Conflicts of interest

Operators disclose material conflicts in manifest notes. A second maintainer should review runs involving the operator's own agent/model.

## Unofficial labeling

Public API uploads are stored and displayed as unofficial. The public upload path rejects `metadata.official=true`.
