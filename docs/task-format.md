# Task format

HermesBench tasks are Markdown files with YAML frontmatter followed by named `##` sections. Existing task packs remain parse-compatible, but new or revised tasks should satisfy the quality lint emitted by `hermesbench validate-tasks`.

## Required frontmatter

Required fields: `id`, `title`, `category`, `wave`, `visibility`, `created_at`, `freshness_window`, `expected_human_minutes`, `difficulty`, `required_toolsets`, `grading_type`, `timeout_seconds`, `contamination_notes`, and `safety_notes`.

Recommended quality field:

- `quality_tier`: one of `gold`, `silver`, `bronze`, `experimental`, or `needs-review`. If omitted, HermesBench computes a tier from quality lint findings.

## Required quality sections for new tasks

Include these sections after setup:

- `## Failure mode tested` — the concrete behavior the task is intended to catch.
- `## Why hard for agents` — why tool-using agents are likely to fail despite a human being able to solve it.
- `## Overfitting risk` — visible markers or shortcuts and how checks mitigate them.

## Deterministic check quality

Avoid marker-only tasks. A good deterministic check set normally has at least four independent checks and includes both:

- command validation (`command_passes`, `command_contains`, or `command_not_contains`), and
- semantic validation (`json_field`, regex checks, negative assertions, or command output assertions).

`validate-tasks` flags:

- three or fewer deterministic checks,
- tiny or missing fixtures unless `no_fixture_required: true`,
- marker-only artifacts/checks such as only `done.txt`,
- missing command validation, and
- missing semantic validation beyond file existence.

Quality findings are printed as `WARNING` or `ERROR` lines so maintainers can distinguish shallow tasks from structural format failures.

## Non-public and generated packs

The committed `private-holdout` suite is a sample/template pack: it must contain real prompts, fixtures, and deterministic checks, but it is not the maintainer secret pack. Official private packs live outside git and are selected with `HERMESBENCH_PRIVATE_PACK_DIR`, using the same manifest/task layout. Fresh rolling packs should be regenerated with `scripts/create_fresh_wave.py` so dates, dataset ids, policy codes, checksums, and fixture values rotate between waves.
