# Benchmark methodology

HermesBench is a harness for collecting auditable tool-use evidence. It separates **`hermes-core`**, the tools and features shipped in the base Hermes Agent installation, from **`hermes-extended`**, installable/configurable ecosystem tools and integrations. Both scopes require their runtime prerequisites to be available and disclosed.

The task manifests are the source of truth for current inventory and scope. The inventory is a public set of focused probes, not a capability certification for every Hermes Agent feature.

## Behavior grading

Scoring uses execution telemetry and deterministic checks:

- **Trajectory evidence:** telemetry records which requested tool classes were actually invoked during a run.
- **Scope-aware interpretation:** a `hermes-core` result speaks only to shipped Hermes features. An `hermes-extended` result is interpretable only with the enabled toolset, credentials/service state, and environment disclosure. Missing extended tools are environmental skips, not model failures.
- **Scoring:** task scores report observed evidence and deterministic checks. They do not by themselves prove a general model capability claim.
- **Task correctness:** `task_correctness_pass` is true only when every task in the run passes its deterministic checks.
- **Tool capability:** `tool_capability_pass` is true only when every evaluable task invokes all required tool classes, independent of final-answer correctness. If required tasks were unavailable, `tool_capability_evaluable=false` and no pass claim is made.
- **Strict combined gate:** legacy `capability_pass` remains the strict combined gate. It must not be presented as tool capability alone.
- **Runtime classification:** trusted adapter `runtime_issues` are preserved as `runtime_warnings`. A warning does not erase valid deterministic evidence or automatically create an environment skip. Only an explicit trusted `environment_skip` excludes an unavailable attempt.
- **Cost availability:** `cost_telemetry_coverage` reports the fraction of attempted tasks with cost telemetry. `cost_telemetry_status` is `unavailable`, `partial`, `complete_zero`, or `complete`. `complete_zero` means all attempts reported zero, not that inference was independently verified as free. Score-per-dollar claims require `complete` status.
- **Official evidence:** a capability claim requires a maintainer-reviewed archive with result hash, environment metadata, declared scope, and public-safe evidence under [`official-runs/`](official-runs.md).
Only reviewed, archived official runs appear as public capability evidence.
