# Changelog

## Unreleased

- Pivoted the benchmark from a ProjectOps correctness scoreboard to a **minimum-capable-model probe** for Hermes Agent tool coverage.
- Restructured task inventory to only ship `natural-tools-dev` containing 5 capability-focused tool-use tasks.
- Introduced telemetry-based behavior grading: a task passes if the model successfully invokes the required tool classes, rather than grading output artifacts.
- Isolated legacy PyTorch model-probing test files into `src/qwen_mtp_probe/tests/` to prevent default pytest collection errors.
- Added parallel task execution for benchmark runs via `--jobs auto|N`, with isolated per-task sandboxes and ordered result output.
- Made the core `hermesbench` install lightweight by keeping only runtime benchmark dependencies in `[project.dependencies]`.
- Moved heavy legacy model-probing dependencies (`torch`, `transformers`, `accelerate`, `safetensors`) to the optional `ml` extra/dependency group.
- Limited wheel packaging to `src/hermesbench/`; the legacy `src/qwen_mtp_probe/` namespace remains source-tree provenance/research material rather than a shipped HermesBench package.
- Added `REPOSITORY_MAP.md` and clarified provenance, architecture, and legacy namespace docs.

## 0.1.0

Initial public-ready HermesBench scaffold.
