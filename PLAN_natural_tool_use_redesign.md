# HermesBench Natural-Tool-Use Redesign — Implementation Plan

## Goal
Finalize the HermesBench pivot into a **natural-tool-use capability probe** for Hermes Agent. Expand coverage to the full set of Hermes tool/feature classes, fix the behavior grader and adapter to correctly classify and enable toolsets, rewrite the README/docs to be consistent, and ship with smoke tests + a commit.

## Current state (from inspection)
- Suite: `natural-tools-dev` with 5 tasks.
- Behavior grader: `src/hermesbench/graders/behavior.py`.
- Adapter: `src/hermesbench/adapters/hermes.py`.
- Runner: `src/hermesbench/runner.py`.
- README: already pivoted but inconsistent, with legacy ProjectOps wording and stale counts.
- `validate-tasks` reports 10 quality findings: every task has ≤2 checks and tiny/missing fixtures (some need `no_fixture_required: true`).
- Toolset map is missing several Hermes core toolsets (e.g., `image_gen`, `video`, `video_gen`, `tts`, `x_search`, composite sets like `coding`).
- Grader does not recognize `browser_vision`, `computer_use`, `image_generate`, `text_to_speech`, `video_generate`, `video_analyze`, `todo`, `process`, `read_terminal`, `execute_code`, etc.
- CLI `--toolsets` flag may not exist in `hermes chat`; adapter currently uses `--toolsets` which is correct per docs. Need to verify Hermes CLI actually accepts it. If not, pass via `hermes config set` or env.

## Outcome
A concise, concrete plan returned to the parent agent; no code changes made.

## Hermes tool/feature classes to cover
Canonical tool classes for the probe (matching `NATURAL_TOOL_CLASSES` in `src/hermesbench/schemas.py` and Hermes docs):
- `file` — already covered (htu-dev-001)
- `terminal` — already covered (htu-dev-001)
- `web` — already covered (htu-dev-002)
- `browser` — new task required
- `code_execution` — new task required
- `vision` — new task required
- `memory` — already covered (htu-dev-004)
- `todo` — new task required
- `skills` — already covered (htu-dev-003)
- `session_search` — new task required
- `delegation` — already covered (htu-dev-005)
- `clarify` — new task required
- `cronjob` — new task required
- `computer_use` — new task required (gated by cua-driver)

Optional/advanced classes (can add later but not required for v0.1 boundary): `x_search`, `image_gen`, `video`, `video_gen`, `tts`, `homeassistant`, `kanban`, `project`, `mcp_*`.

## Minimal new task set (8 tasks)
All tasks use `category: natural-tool-use`, `grading_type: deterministic`, `tool_use_requirements` with the target class, and at least 4 independent checks to satisfy quality lint.

| ID | Class | Goal | Fixture | Key checks |
|---|---|---|---|---|
| `htu-dev-006-browser-required` | browser | Find a specific number on a static, reliable page (e.g., a local HTML fixture served via `python -m http.server`) and write it to answer. | `fixtures/htu-dev-006-browser-required/index.html` with a hidden number. | `browser_navigate` seen in transcript; artifact exists; artifact contains hidden number; `command_passes` verifies the number. |
| `htu-dev-007-code-execution` | code_execution | Compute a non-trivial result that is much easier with a Python script calling tools, and write it to answer. | `fixtures/htu-dev-007-code-execution/data.csv` with rows to sum. | `execute_code` seen; script output/answer contains correct sum; `command_passes` validates; file exists. |
| `htu-dev-008-vision-required` | vision | Decode a short string shown in a local image (e.g., base64-like text in an image). | `fixtures/htu-dev-008-vision-required/captcha.png` with embedded text. | `vision_analyze` seen; answer contains text; `command_passes` checks the string; artifact exists. |
| `htu-dev-009-todo-list` | todo | User gives 3 sub-tasks. Agent must track them with `todo`, complete them, and write a summary. | `fixtures/htu-dev-009-todo-list/tasks.txt` with 3 items. | `todo` seen; all 3 items checked off or summary contains them; `command_passes` validates; artifact exists. |
| `htu-dev-010-session-search` | session_search | Prompt instructs the agent to recall a fact from a previous session, but no local context is given. Requires `session_search`. | No fixture (set `no_fixture_required: true`). | `session_search` seen; answer contains a known string from prior sessions; artifact exists; `command_passes` checks. |
| `htu-dev-011-clarify-required` | clarify | Prompt is ambiguous about required output format. Agent must ask for clarification before proceeding. | `fixtures/htu-dev-011-clarify-required/instructions.txt` with the ambiguous prompt. | `clarify` seen; final answer only after clarification; artifact exists; command checks for the requested format. |
| `htu-dev-012-cronjob-reminder` | cronjob | Schedule a recurring job that writes a specific marker file. | No fixture (set `no_fixture_required: true`). | `cronjob` seen; a cron entry is created; `command_passes` lists the job; artifact exists or `cronjob list` output contains task name. |
| `htu-dev-013-computer-use` | computer_use | Open a calculator app (or local GUI element) via `computer_use` and retrieve a number. | No fixture (set `no_fixture_required: true`). | `computer_use` seen; answer contains the expected number; artifact exists; `command_passes` checks. |

This brings the suite from 5 to 13 tasks and covers all 14 canonical classes.

## Grader fixes (`src/hermesbench/graders/behavior.py`)
1. Expand `_BEHAVIOR_TOOLS` mapping:
   - Add `browser_vision` → `browser`
   - Add `process`, `read_terminal` → `terminal`
   - Add `execute_code` → `code_execution` (already present, confirm)
   - Add `todo` → `todo` (already present, confirm)
   - Add `image_generate`, `text_to_speech`, `video_generate`, `video_analyze` → `vision`, `image_gen`, `video_gen`, `video`, `tts` as extended classes or map to canonical ones.
   - Add `computer_use` → `computer_use` (already present, confirm)
   - Add `session_search` → `session_search` (already present, confirm)
   - Add `delegate_task` → `delegation` (already present, confirm)
2. Add robust namespaced matching for `mcp__` prefix and `mcp_<server>_` tools (already returns `web` for `mcp__` prefix; broaden to not force `web` for all MCP tools).
3. Fix `score_tool_use` logic: currently returns `0.0` when `required` is empty, which is correct for capability tasks. But if `required` is non-empty and missing is empty, score is 1.0 — correct. No change needed there.
4. Ensure fallback regex picks up `tool_name.completed` lines for new tools.

## Adapter fixes (`src/hermesbench/adapters/hermes.py`)
1. Expand `_TOOLSET_MAP` to include all core toolsets from Hermes docs:
   - `browser`, `clarify`, `code_execution`, `cronjob`, `delegation`, `file`, `memory`, `session_search`, `skills`, `terminal`, `todo`, `vision`, `computer_use`, `web`, `x_search`, `image_gen`, `video_gen`, `video`, `tts`, `homeassistant`, `kanban`, `project`.
2. Verify `--toolsets` is accepted by `hermes chat`. If not, refactor to:
   - Write a temporary `config.yaml` with `toolsets: [...]` and pass `--config <path>`; or
   - Set `HERMES_TOOLSETS` env var if supported; or
   - Use `hermes config set toolsets [...]` before invocation (risky global side effect).
   Preferred: pass `--toolsets` since docs explicitly show it. If smoke test fails, switch to temp config.
3. Ensure `all` resolves to the exact set of toolsets we want for a task, not literally every toolset (Hermes docs note `all` expands to every registered toolset, but some gated ones still need backend setup). For benchmark safety, keep explicit list for `all`.
4. Add a `--no-confirm` or equivalent if Hermes CLI requires user approval for dangerous commands; otherwise long runs may hang.
5. Capture `AgentRun.tool_events` from the Hermes transcript (currently empty list) and pass it to the runner so behavior grading can be double-checked against structured data.

## Runner fixes (`src/hermesbench/runner.py`)
1. No major changes, but ensure `_used_tool_classes` is called after the adapter returns `tool_events` and the behavior grader can consume both transcript and structured events.
2. Consider storing `tool_classes_observed` in `TaskResult` already present; good.

## Task quality fixes for existing 5 tasks
Every existing task currently fails the quality lint (only 2-3 checks). Add at least 4 independent checks per task and mark `no_fixture_required: true` where fixtures are intentionally tiny.

Examples:
- `htu-dev-001-file-and-terminal-self-serve`: add `command_passes` verifying sum, `artifact_contains` with exact answer, `command_passes` checking file was read, and a `command_passes` checking the command used includes `sum`/`awk`.
- `htu-dev-002-web-search-required`: add `command_passes` checking answer is non-empty and has version-like pattern, `artifact_contains` with regex, `artifact_not_contains` checking for “unknown”, and a `command_passes` that greps for version number.
- `htu-dev-003-use-a-skill`: add `artifact_contains` with decoded value, `command_passes` verifying decoded string, `command_passes` checking skill name in transcript, and `artifact_exists`.
- `htu-dev-004-memory-recall`: add checks for memory tool in transcript, artifact contains secret, and command checks.
- `htu-dev-005-delegate-parallel-subtasks`: add command checks verifying both subagents were used and the combined sum is correct.

Also add `no_fixture_required: true` to `htu-dev-002` (no fixture) and possibly others where the fixture is intentionally small.

## README rewrite
Target file: `README.md`.

Changes needed:
1. Update the task count badge from `tasks-5-orange` to `tasks-13-orange`.
2. Remove lingering ProjectOps language (`projectops`, `qwen_mtp_probe`, legacy training references) or relegate them to a Provenance section.
3. In the “What makes it different” list, ensure the tool-class list matches the canonical 14 classes and does not mention removed/legacy ones.
4. Update the `natural-tools-dev` table to say 13 tasks.
5. Clarify the “minimum-capable-model” scoring: the boundary is the smallest model that passes every required tool class in the suite, not the smallest overall.
6. Clean up the CLI reference section: remove `upload`, `serve-api`, `archive-official` if not fully implemented or mark as experimental. Keep only commands that are tested.
7. Add a “Task coverage” section listing each tool/feature class and the task that probes it.
8. Fix the duplicate “Adding tasks” step 6 (two step 6s).
9. Ensure the “Development checks” block matches actual smoke commands.

## Documentation updates
- `docs/task-format.md`: update to mention `tool_use_requirements`, `required_toolsets`, `no_fixture_required`, and the 4-check minimum.
- `docs/methodology.md`: rewrite to describe capability-first telemetry grading, false-done penalties, and minimum-capable-model boundary.
- `docs/PROCESS_STATUS.md`: update status to reflect natural-tool-use pivot and remaining work.
- Remove or archive stale ProjectOps/legacy training docs if they are not part of the HermesBench package. At minimum, add a header to them noting they are historical.

## Smoke tests and commit
1. Run `uv run hermesbench validate-tasks` and fix remaining errors/warnings.
2. Run `uv run pytest tests/test_hermesbench_core.py -q`.
3. Run `uv run hermesbench run --agent mock --suite natural-tools-dev --output-dir /tmp/hermesbench-results`.
4. Run `uv run hermesbench score /tmp/hermesbench-results/*.json`.
5. If any Hermes CLI smoke test is attempted, do it with a local model and `--jobs 1` to verify the toolset enablement.
6. Commit with a clear message: `feat: finalize natural-tool-use redesign — 13 tasks, full tool-class coverage, README/docs rewrite`.

## Concrete file paths and task IDs
- New tasks: `tasks/natural-tools-dev/htu-dev-006-browser-required.md`, `htu-dev-007-code-execution.md`, `htu-dev-008-vision-required.md`, `htu-dev-009-todo-list.md`, `htu-dev-010-session-search.md`, `htu-dev-011-clarify-required.md`, `htu-dev-012-cronjob-reminder.md`, `htu-dev-013-computer-use.md`
- Fixtures: `fixtures/htu-dev-006-browser-required/index.html`, `fixtures/htu-dev-007-code-execution/data.csv`, `fixtures/htu-dev-008-vision-required/captcha.png`, `fixtures/htu-dev-009-todo-list/tasks.txt`, `fixtures/htu-dev-011-clarify-required/instructions.txt`
- Code: `src/hermesbench/graders/behavior.py`, `src/hermesbench/adapters/hermes.py`, `src/hermesbench/runner.py`, `src/hermesbench/schemas.py` (expand `NATURAL_TOOL_CLASSES` if needed)
- Docs: `README.md`, `docs/task-format.md`, `docs/methodology.md`, `docs/PROCESS_STATUS.md`
- Manifest: `tasks/manifest.yaml` (add 8 entries)

## Open questions / risks
- Does `hermes chat --toolsets` actually work in the installed CLI? Smoke test required.
- `computer_use` requires `cua-driver` on PATH; may be skipped in CI unless installed. Should be marked as optional/conditional in CI.
- `cronjob` and `clarify` tasks may require interactive or daemon state; need to design fixtures that avoid user input.
- `vision` task needs an image fixture; generate a simple PNG with embedded text (e.g., with Pillow or a stub image).
- `browser` task may need a local HTTP server; the agent can start one, or the runner can serve the fixture. Simpler: instruct the agent to open the file via `file://` URL so `browser_navigate` works without a server.

## Recommended order of implementation
1. Update schemas/grader/adapter to know all tool classes and toolsets.
2. Add the 8 new tasks + fixtures.
3. Fix the 5 existing tasks’ quality lints.
4. Update `manifest.yaml`.
5. Rewrite README and docs.
6. Run smoke tests and commit.
