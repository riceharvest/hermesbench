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

## Current prepared HF artifacts

The first usable HF sources are now converted and ready:

- Active train-compatible: `data/examples/hermes_hf_openhands_swe.v0.jsonl` — 300 rows from `SWE-Gym/OpenHands-SFT-Trajectories` success split.
- Active train-compatible: `data/examples/hermes_hf_openthoughts_terminal.v0.jsonl` — 300 rows from `open-thoughts/OpenThoughts-Agent-v1-SFT`.
- Quarantined source-ready: `data/raw/hf/hermes_hf_toolcall_source_ready.v0.jsonl` — 300 rows from TauBench/Qwen ToolScale with domain tool calls stored in metadata, not active Hermes `ACTION` targets.

The active-compatible HF rows have been added to `data/processed/hermes_v0_train.jsonl`, bringing active SFT to 7,032 rows. The quarantined source-ready rows are intentionally excluded from active SFT until the tool namespace/mix policy is decided.

Converter scripts:

- `scripts/convert_hf_openhands_swe.py`
- `scripts/convert_hf_openthoughts_terminal.py`
- `scripts/convert_hf_toolcall_sources.py`

Quality reports:

- `reports/hermes-hf-openhands-swe-quality.json`
- `reports/hermes-hf-openthoughts-terminal-quality.json`
- `reports/hermes-hf-toolcall-sources-quality.json`

See detailed subagent reports:
- `reports/hf-openhands-swe-usability.md`
- `reports/hf-terminal-agent-usability.md`
- `reports/hf-qwen-taubench-hermes-usability.md`
