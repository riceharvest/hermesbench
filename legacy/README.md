# Legacy research namespace

This directory documents source-tree material that predates the HermesBench public benchmark identity.

The historical working repository was named `qwen-mtp-probe` and included Qwen/MTP model-probing, conversion, SFT, and evaluation experiments. Those files are preserved for provenance and auditability, but they are not the HermesBench runtime package.

## Packaging boundary

- HermesBench packages only `src/hermesbench/`.
- `src/qwen_mtp_probe/` is intentionally excluded from the HermesBench wheel.
- Legacy research scripts may still import `qwen_mtp_probe` when run from a source checkout with appropriate `PYTHONPATH`/`uv run` context.
- Heavy ML dependencies for those scripts (`torch`, `transformers`, `accelerate`, `safetensors`) are optional and live under the `ml` extra/dependency group.

## Runtime boundary

Do not treat legacy Qwen/MTP files as task definitions, benchmark graders, or a public API. The public benchmark assets are `tasks/`, `fixtures/`, `benchmark_versions/`, docs, website scaffolding, and the `hermesbench` package.
