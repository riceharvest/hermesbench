# Architecture

`src/hermesbench` contains the installable HermesBench package: CLI, task parser, runner, adapters, graders, schemas, scoring, API/storage helpers, and official-run archive utilities. Tasks live under `tasks/` with a manifest and reusable template. Fixtures are copied into isolated temp workdirs per task. Results are normalized JSON and can be aggregated locally or uploaded later.

The wheel packaging boundary is deliberate: HermesBench ships `src/hermesbench/` only, keeping the core install small.

Dependency tiers:

- Core runtime: lightweight CLI/benchmark dependencies only (`pyyaml`).
- Dev/test: `pytest` via the `dev` dependency group.
