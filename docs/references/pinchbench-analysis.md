# PinchBench reference analysis

Inspected `pinchbench/skill`, `pinchbench/api`, and `pinchbench/leaderboard`.

## Copy conceptually
- Separate benchmark task repository, API, and leaderboard concerns.
- Markdown task files with human-readable prompts and deterministic grading hooks.
- Public leaderboard positioning, badges, and result detail pages.
- Upload/submission flow with official-run reservation.

## Avoid
- Hard-coding one agent family. HermesBench uses adapters for Hermes CLI, generic shell commands, and mock tests.
- Treating public static tasks as sufficient. HermesBench documents public/dev, private holdout, fresh rolling waves, and stable anchors.
- Letting LLM judge scores replace objective execution checks.

## HermesBench differences
- Task metadata includes contamination risk, freshness window, required toolsets, human baselines, and false-done risk.
- Scoring tracks verification compliance, false-done rate, timeouts, tool calls, wall time, and optional cost.
- Public/dev suite works without credentials; hidden checks are supported architecturally but redacted from public output.
