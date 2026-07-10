# Changelog

## Unreleased

- Pivoted the benchmark from a ProjectOps correctness scoreboard to a **minimum-capable-model probe** for Hermes Agent tool coverage.
- Restructured the combined `natural-tools-dev` development inventory to 38 scoped tool-use probes (3 core CLI and 35 integration probes).
- Introduced telemetry-based behavior grading: a task passes if the model successfully invokes the required tool classes, rather than grading output artifacts.
- Removed legacy model-probing packages and data; the repository now contains only the benchmark runtime and website.
- Added parallel task execution for benchmark runs via `--jobs auto|N`, with isolated per-task sandboxes and ordered result output.
- Made the core `hermesbench` install lightweight by keeping only runtime benchmark dependencies in `[project.dependencies]`.
- Added `REPOSITORY_MAP.md` and clarified methodology, architecture, and deployment docs.
- Collapsed the API to a single authenticated submission lane: `POST /v1/results` and `GET /v1/leaderboard`.

## 0.1.0

Initial public-ready HermesBench scaffold.
