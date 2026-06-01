# Changelog

## Unreleased

- Made the core `hermesbench` install lightweight by keeping only runtime benchmark dependencies in `[project.dependencies]`.
- Moved heavy legacy model-probing dependencies (`torch`, `transformers`, `accelerate`, `safetensors`) to the optional `ml` extra/dependency group.
- Moved `pytest` out of runtime dependencies and into test/dev extras and the `dev` dependency group so `uv run pytest` remains supported for contributors.
- Limited wheel packaging to `src/hermesbench/`; the legacy `src/qwen_mtp_probe/` namespace remains source-tree provenance/research material rather than a shipped HermesBench package.
- Added `REPOSITORY_MAP.md` and clarified provenance, architecture, and legacy namespace docs.
- Corrected public task counts to 50 manifest entries total, including 35 public-dev tasks.
- Added fresh-wave, anchor promotion, website deployment, release, and launch-readiness workflows.
- Added static leaderboard/result demo data and a multi-section website scaffold.

## 0.1.0

Initial public-ready HermesBench scaffold with 35 public/dev tasks, 50 manifest entries total, CLI runner, scoring, docs, CI, and website scaffold.
