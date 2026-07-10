# Benchmark methodology

HermesBench is an early-stage harness for collecting auditable tool-use evidence. It separates the portable **core CLI** surface from optional **integrations**. The core CLI covers behavior that can be exercised in a local runner; integrations include browser automation, connected services, desktop control, and configured skills, and require their runtime prerequisites to be available and disclosed.

The current `natural-tools-dev` inventory contains 38 development probes. It is a public development suite, not a completed capability certification for every Hermes Agent feature.

## Behavior grading

Scoring uses execution telemetry and deterministic checks:

- **Trajectory evidence:** telemetry records which requested tool classes were actually invoked during a run.
- **Scope-aware interpretation:** a core-CLI result speaks only to that core scope. An integration result is interpretable only with the enabled toolset, credentials/service state, and environment disclosure. Missing integrations are environmental skips, not model failures.
- **Scoring:** task scores report observed evidence and deterministic checks. They do not by themselves prove a general model capability claim.
- **Official evidence:** a capability claim requires a maintainer-reviewed archive with result hash, environment metadata, declared scope, and public-safe evidence under [`official-runs/`](official-runs.md).
Until official scoped archives exist, the website shows no public results. Only reviewed, archived official runs appear as capability evidence.
