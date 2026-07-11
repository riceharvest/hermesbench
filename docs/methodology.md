# Benchmark methodology

HermesBench is an early-stage harness for collecting auditable tool-use evidence. It separates **`hermes-core`**, the tools and features shipped in the base Hermes Agent installation, from **`hermes-extended`**, installable/configurable ecosystem tools and integrations. Both scopes require their runtime prerequisites to be available and disclosed.

The current two-suite inventory contains 38 development probes: 19 in each scope. It is a public development inventory, not a completed capability certification for every Hermes Agent feature.

## Behavior grading

Scoring uses execution telemetry and deterministic checks:

- **Trajectory evidence:** telemetry records which requested tool classes were actually invoked during a run.
- **Scope-aware interpretation:** a `hermes-core` result speaks only to shipped Hermes features. An `hermes-extended` result is interpretable only with the enabled toolset, credentials/service state, and environment disclosure. Missing extended tools are environmental skips, not model failures.
- **Scoring:** task scores report observed evidence and deterministic checks. They do not by themselves prove a general model capability claim.
- **Official evidence:** a capability claim requires a maintainer-reviewed archive with result hash, environment metadata, declared scope, and public-safe evidence under [`official-runs/`](official-runs.md).
Until official scoped archives exist, the website shows no public results. Only reviewed, archived official runs appear as capability evidence.
