# HermesBench Natural-Tool-Use Expansion Plan

## Scope

Finalize the `natural-tools-dev` suite redesign by adding the missing tool-class probes, tightening the behavior grader, and updating the README. No code is written yet; this is the implementation plan.

---

## 1. New tasks to add

Add one task per missing tool class. All tasks follow the existing template (`tasks/TASK_TEMPLATE.md`), are `category: natural-tool-use`, `wave: natural-tools-v0-2026-07`, `visibility: public`, `grading_type: deterministic`, and declare `tool_use_requirements` with the target class. IDs continue the `htu-dev-XXX` sequence from `005`.

| ID | `tool_use_requirements` | `required_toolsets` | One-sentence description |
|---|---|---|---|
| `htu-dev-006-todo-track-subtasks` | `todo` | `todo`, `file`, `terminal` | Ask the agent to plan and track progress toward a multi-step local goal; it must create or update a todo list before producing the final answer. |
| `htu-dev-007-code-execution-compute` | `code_execution` | `code_execution`, `file` | Ask the agent to compute a non-trivial aggregate from a fixture that is easier to solve with a small Python script than by hand; it must run code. |
| `htu-dev-008-browser-extract-fact` | `browser` | `browser`, `web`, `file` | Ask the agent to confirm a current fact that is only verifiable by navigating a known public page; it must use browser tools, not just web search. |
| `htu-dev-009-web-extract-structured` | `web` | `web`, `file` | Ask the agent to extract a structured datum from a known public URL; it must call `web_extract`/`mcp__fetch__fetch` rather than relying on memory. |
| `htu-dev-010-session-search-recall` | `session_search` | `session_search`, `file` | Ask the agent to recall a fact from a previous session topic stored in the session DB; it must use `session_search`. |
| `htu-dev-011-clarify-before-answer` | `clarify` | `clarify`, `file` | Give the agent an ambiguous instruction with a missing critical detail; it must ask the user a clarifying question via the clarify tool before proceeding. |
| `htu-dev-012-cronjob-schedule-reminder` | `cronjob` | `cronjob`, `file` | Ask the agent to schedule a lightweight periodic check; it must use the cronjob tool to create or inspect a cron entry. |
| `htu-dev-013-computer-use-ui-action` | `computer_use` | `computer_use`, `file` | Ask the agent to inspect a screenshot or perform a simple UI action in a desktop app; it must use `computer_use` (capture/click). |
| `htu-dev-014-vision-image-analysis` | `vision` | `vision`, `file` | Provide an image fixture and ask a question answerable only from the image; the agent must call a vision tool. |
| `htu-dev-015-image-gen-create-asset` | `image_gen` | `image_gen`, `file` | Ask the agent to generate an image matching a text specification; it must use an image-generation tool. |

Notes:
- `browser` and `web` are kept distinct: `008` forces browser navigation/interaction, while `009` forces URL content extraction. This exercises both `browser_*` and `web_extract`/`mcp__fetch__fetch` telemetry.
- `vision` and `image_gen` are separate classes in the adapter (`vision`/`image_gen`) but the schema only lists `vision` under `NATURAL_TOOL_CLASSES`; add `image_gen` to `NATURAL_TOOL_CLASSES` so the new task validates.
- Each task needs a local fixture under `fixtures/<task-id>/public/` unless `no_fixture_required: true` is justified (e.g., `008`, `009`, `015` may use no fixture or a tiny prompt-only setup).

---

## 2. Schema and code fixes

### 2.1 `src/hermesbench/schemas.py`
- Add `image_gen` to `NATURAL_TOOL_CLASSES` so `htu-dev-015` passes `_validate_tool_use_requirements`.
- Consider adding `x_search`/`messaging` to `NATURAL_TOOL_CLASSES` only if tasks are added; otherwise leave them adapter-only.

### 2.2 `src/hermesbench/graders/behavior.py`
- Missing mappings: `_BEHAVIOR_TOOLS` has no entry for `vision_analyze` (only present) or `generate_image`, `image_gen`, `computer_use`, `cronjob`, `session_search`, etc. Add canonical names used by Hermes telemetry, e.g.:
  - `vision_analyze` → `vision` (already present, but verify `image_gen` mapping)
  - `generate_image` / `image_gen` / `create_image` → `image_gen`
  - `computer_use` / `computer_use_capture` / `computer_use_click` → `computer_use`
  - `cronjob` / `cronjob_schedule` / `cronjob_list` → `cronjob`
  - `session_search` → `session_search`
  - `clarify` / `ask_user` → `clarify`
  - `todo` / `todo_create` / `todo_list` → `todo`
  - `execute_code` / `run_python` / `repl` → `code_execution`
  - `browser_navigate` / `browser_snapshot` / `browser_click` / `browser_type` → `browser` (already present)
- Harden `_extract_tool_events` to handle JSONL files, nested telemetry arrays, and lowercase key variants (`tool`, `tool_name`, `name`).
- Make `score_tool_use` return a partial score or at least richer detail when some required classes are observed but not all; currently it is binary. Keep the binary effective pass but expose a `coverage_ratio` in details so the leaderboard can report progress.

### 2.3 `src/hermesbench/adapters/hermes.py`
- `_TOOLSET_MAP` already contains `image_gen`, `computer_use`, `cronjob`, `session_search`, `clarify`, `todo`, `code_execution`, `vision`, `browser`, `web`, etc. Verify it is exhaustive for the new toolsets and add any missing aliases.
- `_CAPABILITY_TOOLSETS` also looks complete, but add `image_gen` to `_CAPABILITY_TOOLSETS` if not already present (it is already present).
- Consider adding a `--no-toolsets` fallback warning when a task requests a toolset not present in the CLI; current behavior silently drops it.

### 2.4 `src/hermesbench/runner.py`
- The `_used_tool_classes` function relies on `score_tool_use(..., [])`. This works but is slightly indirect; no change needed unless behavior grader changes.
- When `task.metadata['tool_use_requirements']` is missing, `effective_score = max(0.0, raw_score-behavior_penalty)` is correct. When present, behavior score gates pass. Keep this logic but ensure `behavior_score` is reported in `TaskResult` metadata.

### 2.5 `src/hermesbench/tasks.py`
- Quality lint currently errors if no `command_*` or semantic checks. New tasks must include at least four checks and at least one `command_*` and one semantic check. This is enforced by existing lint, so new task authors must comply.
- Add `image_gen` to the `NATURAL_TOOL_CLASSES` set as noted above.

---

## 3. Manifest update

Edit `tasks/manifest.yaml` to append the 10 new entries under `suites.natural-tools-dev.tasks`. The suite version should bump from `0.1.0` to `0.2.0` and the manifest `version` from `0.3.0` to `0.4.0`.

Example entry format (preserve existing style):

```yaml
    - id: htu-dev-006-todo-track-subtasks
      path: natural-tools-dev/htu-dev-006-todo-track-subtasks.md
      category: natural-tool-use
      visibility: public
```

Repeat for `007` through `015`.

---

## 4. Fixture plan

Create a fixture directory per task where applicable:

| Task | Fixture contents |
|---|---|
| `006` | `data/goal.txt` describing the multi-step goal; tiny so the model is forced to plan. |
| `007` | `data/numbers.csv` with values to aggregate; answer is easier via Python. |
| `010` | `data/session_topic.txt` with a topic the agent must search sessions for; runner may optionally seed a fake session entry. |
| `011` | `data/ambiguous_request.txt` with a deliberately underspecified ask. |
| `012` | `data/schedule.txt` with the task to schedule; no real system side effects expected. |
| `013` | `data/screenshot.png` or a placeholder HTML/app reference; may require a desktop environment in real runs. |
| `014` | `data/image.png` with a simple visual question (e.g., count shapes, read text). |
| `015` | No fixture; prompt-only generation task. |
| `008`/`009` | Optional tiny fixture with target URL or query hint; otherwise no fixture. |

For tasks that cannot run in CI without credentials or a desktop (`008`, `009`, `013`, `015`), mark them as requiring credentials or an environment and set `no_fixture_required: true` if no local fixture is needed. Add a `skip_ci` note in the task metadata or in `docs/ci-notes.md` if necessary.

---

## 5. README rewrite

Update `README.md` in these sections:

- **Badge**: change `tasks-5` to `tasks-15`.
- **Tool-class coverage** bullet: replace the list with the full 15-class set: `file`, `terminal`, `web`, `browser`, `code_execution`, `vision`, `image_gen`, `memory`, `todo`, `skills`, `session_search`, `delegation`, `clarify`, `cronjob`, `computer_use`.
- **Task suites table**: update `natural-tools-dev` count to 15, add a note that some tasks require external credentials or a desktop environment.
- **Quick start**: verify commands still work; no change expected unless CLI flags change.
- **Current status**: mention the suite is now at v0.2.0 and covers the full natural-tool-use surface.
- **Adding tasks**: mention the new tool-class list and fixture guidance for credential/desktop tasks.

---

## 6. Tests and validation

After implementation, run:

```bash
uv run hermesbench validate-tasks
uv run pytest tests/test_hermesbench_core.py -q
```

Expected updates to tests:
- `test_task_suite_has_natural_tools_dev_tasks` asserts `len(tasks) == 5`; update to `15`.
- Add a new test: `test_natural_tools_dev_covers_all_tool_classes` verifying that every class in `NATURAL_TOOL_CLASSES` appears in at least one task's `tool_use_requirements`.
- Add a new test: `test_behavior_grader_maps_new_tool_classes` that supplies synthetic transcripts containing `todo`, `computer_use`, `image_gen`, etc., and confirms the observed class is recognized.

---

## 7. Files touched

- `src/hermesbench/schemas.py` — add `image_gen` to `NATURAL_TOOL_CLASSES`.
- `src/hermesbench/graders/behavior.py` — add missing tool-name mappings and telemetry parsing improvements.
- `src/hermesbench/adapters/hermes.py` — verify toolset/capability maps; add missing aliases if any.
- `tasks/manifest.yaml` — bump versions and add 10 entries.
- `tasks/natural-tools-dev/htu-dev-00{6..15}*.md` — 10 new task files.
- `fixtures/htu-dev-00{6..14}/public/` — fixture files as listed above.
- `tests/test_hermesbench_core.py` — update count and add coverage tests.
- `README.md` — update counts, tool-class list, and suite description.

---

## 8. Order of execution

1. Patch schema + behavior grader + adapter maps.
2. Draft task markdowns and fixtures.
3. Update manifest.
4. Update tests.
5. Run `validate-tasks` and `pytest`; fix quality lint errors.
6. Rewrite README and run final validation.
