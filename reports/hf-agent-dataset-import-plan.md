# HF agent dataset import plan for Hermes v0

Subagents inspected sampled HF datasets for fit with the current Hermes v0 SFT target: compact GPT-like tool-use traces that maximize successful agent steps per reasoning token.

## Verdict

No inspected dataset is directly usable as raw SFT input. Several are usable after deterministic conversion, filtering, and CoT compression.

## Import priority

### 1. Import prototype: `SWE-Gym/OpenHands-SFT-Trajectories`

Verdict: **best first converter target**.

Why:
- success split (`train.success.oss`);
- repo/computer interaction is close to Hermes Agent;
- tools map cleanly: `execute_bash` -> `terminal`, `str_replace_editor view` -> `read_file`/`search_files`, edits -> `patch`/`write_file`;
- small enough to prototype quickly.

Rules:
- strip OpenHands system/tool docs;
- convert one assistant action at a time;
- prefer ACTION-only for obvious file/terminal operations;
- use `SCRATCH<=32` only for decision pivots;
- require license/provenance gate before large import.

### 2. Import with low ratio: `jkazdan/taubench_traces_training_data`

Verdict: **usable for generic tool-call discipline**, not core repo-agent behavior.

Why:
- clean OpenAI-style `tool_calls` + explicit `tool` results;
- good for lookup-before-answer, tool-result-grounded finals, confirmation-before-write;
- small and easy to convert.

Rules:
- map `tool_calls[].function` -> `ACTION <tool> {json}`;
- drop/convert any `think` pseudo-tool;
- require explicit user confirmation before write actions;
- cap mix ratio because domain is customer-service, not Hermes repo/terminal work.

### 3. Selective import: `open-thoughts/OpenThoughts-Agent-v1-SFT`

Verdict: **high-value terminal-agent behavior, but verbose**.

Why:
- Terminal-Bench-like Linux command-line tasks;
- strong relevance to Hermes action discipline;
- assistant turns include command batches and task completion markers.

Rules:
- delete `analysis`/`plan` by default;
- convert commands to `ACTION terminal` or native Hermes tools;
- keep only coherent, verified command/result turns;
- reject rows that create unnecessary fixtures or mutate environment without need.

### 4. Prototype only: `zake7749/Qwen-3.6-plus-agent-tool-calling-trajectory`

Verdict: **use for conversion experiments, not bulk v0 import yet**.

Why:
- same Qwen family and has `score`/`reward` fields;
- useful for `reasoning_content` -> compact scratch compression;
- but sampled rows include low `reward=0.0`, customer-service domains, user-side reasoning, and write-action policy risks.

Rules:
- require high score/reward;
- drop user-side reasoning;
- compact assistant `reasoning_content` only when it preserves policy/auth/entity state;
- do not mix heavily into repo-agent v0.

## Reject/direct-risk sources

### `nebius/SWE-agent-trajectories`

Reject for positive v0 SFT based on local samples: all sampled rows had `target=false`. Keep only for negative preference/failure-analysis mining.

### `AmanPriyanshu/...hermes_reasoning_tool_use...`

Reject for direct v0 SFT. It explicitly trains long `<think>` and XML wrappers. Useful only as a stress test for compression.

### `AmanPriyanshu/...text_to_terminal_v2...`

Useful only as cautious single-command mining. Strip almost all `<think>`; filter broad/risky shell commands.

### `smolagents/hermes-function-calling-v1-formatted-code-agent`

Low priority. Mostly domain API function calls in `<code>` blocks, not Hermes repo/terminal behavior.

## Compact CoT conversion contract

Conversion should produce only:

```text
ACTION tool {"valid":"json"}
```

or:

```text
SCRATCH<=32:
One short decision pivot.

ACTION tool {"valid":"json"}
```

or:

```text
FINAL: concise verified answer
```

`SCRATCH<=96` is allowed only for separately tagged high-value teacher traces when compressing to 32 words would lose required state dependencies.

Never keep raw `<think>`, OpenThoughts `analysis`/`plan`, OpenHands private `think`, XML wrappers, OpenAI call IDs, or verbose self-talk.

## Concrete next implementation step

Build a converter prototype for `SWE-Gym/OpenHands-SFT-Trajectories` first:

1. Download/sample the success split.
2. Convert 100-300 assistant action turns into candidate Hermes compact rows.
3. Add `source_dataset`, `source_id`, `source_style`, and `conversion_notes` metadata outside the `messages` target.
4. Run existing data alignment gates plus a new source-specific test:
   - no raw `<function=...>` / `<think>` / `analysis` / `plan` in assistant targets;
   - every action parses as Hermes JSON;
   - no train/eval prompt overlap;
   - no raw secrets;
   - scratch budget respected.
5. Manually inspect a 30-row sample before adding to active training.

See detailed subagent reports:
- `reports/hf-openhands-swe-usability.md`
- `reports/hf-terminal-agent-usability.md`
- `reports/hf-qwen-taubench-hermes-usability.md`
