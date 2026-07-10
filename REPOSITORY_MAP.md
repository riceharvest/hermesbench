# Repository map

HermesBench is the public benchmark identity of this repository. The repository was initialized from an older `qwen-mtp-probe` working tree, so some legacy research files remain for auditability, but the installable package and runtime surface are intentionally limited.

## Installable package

- `src/hermesbench/` — the only package included in HermesBench wheels/sdists. Contains the CLI, task parser, runner, adapters, graders, scoring, API/storage helpers, and official-run archive utilities.
- `hermesbench` console script — entrypoint for validation, runs, scoring, export/upload, API serving, and official archive helpers.

## Benchmark assets

- `tasks/manifest.yaml` — manifest defining the active suite and tasks.
- `tasks/natural-tools-dev/` — 38 development probes spanning core CLI and integration tool classes.
- `fixtures/` — deterministic local fixtures copied into isolated task workdirs.

## Docs and site

- `docs/` — methodology, governance, architecture, API, and deployment docs.
- `website/` — leaderboard and result display site (static frontend + submission API).
- `CHANGELOG.md` — human-facing release/change notes.
