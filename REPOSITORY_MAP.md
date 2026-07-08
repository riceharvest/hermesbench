# Repository map

HermesBench is the public benchmark identity of this repository. The repository was initialized from an older `qwen-mtp-probe` working tree, so some legacy research files remain for auditability, but the installable package and runtime surface are intentionally limited.

## Installable package

- `src/hermesbench/` — the only package included in HermesBench wheels/sdists. Contains the CLI, task parser, runner, adapters, graders, scoring, API/storage helpers, and official-run archive utilities.
- `hermesbench` console script — entrypoint for validation, runs, scoring, export/upload, API serving, and official archive helpers.

## Benchmark assets

- `tasks/manifest.yaml` — manifest defining the active suite and tasks.
- `tasks/natural-tools-dev/` — 5 open-ended capability probes for file, terminal, web, browser, code execution, vision, memory, todo, skills, delegation, and more.
- `fixtures/` — deterministic local fixtures copied into isolated task workdirs.

## Docs and site

- `docs/` — methodology, governance, architecture, provenance, API, and deployment docs.
- `website/` — static landing/leaderboard scaffold and demo data.
- `CHANGELOG.md` — human-facing release/change notes.

## Legacy/provenance material

- `src/qwen_mtp_probe/` — legacy Qwen/MTP model-probing research namespace. It is preserved in the source tree for provenance and local research, but it is not packaged as HermesBench and is not part of the benchmark runtime API.
- `data/eval/hermes_v0_eval.jsonl` and related conversion/training scripts — historical evaluation/SFT artifacts that informed HermesBench design. They may need optional ML dependencies (`torch`, `transformers`, `accelerate`, `safetensors`) and should not be treated as required benchmark dependencies.
- top-level `modal_*` and selected `scripts/` files — legacy experiment helpers retained for auditability.

## Dependency policy

A core HermesBench install stays lightweight and supports validation, mock/shell/Hermes CLI runs, scoring, and local API/storage tests without model stacks. Heavy model dependencies live in optional extras/dependency groups (`ml`), and test tooling lives in the development/test extras/groups.
