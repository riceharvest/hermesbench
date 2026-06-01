# Architecture

`src/hermesbench` contains the installable HermesBench package: CLI, task parser, runner, adapters, graders, schemas, scoring, API/storage helpers, and official-run archive utilities. Tasks live under `tasks/` with a manifest and reusable template. Fixtures are copied into isolated temp workdirs per task. Results are normalized JSON and can be aggregated locally or uploaded later.

The wheel packaging boundary is deliberate: HermesBench ships `src/hermesbench/` only. The historical `src/qwen_mtp_probe/` namespace remains in the source tree as legacy model-probing/provenance material, not as benchmark runtime code. This keeps the core install small and avoids pulling model stacks into users who only want to validate tasks, run adapters, and score results.

Dependency tiers:

- Core runtime: lightweight CLI/benchmark dependencies only (`pyyaml`).
- Dev/test: `pytest` via the `dev` dependency group or `test`/`dev` extras.
- Legacy ML research: `torch`, `transformers`, `accelerate`, and `safetensors` via the `ml` extra/dependency group.
