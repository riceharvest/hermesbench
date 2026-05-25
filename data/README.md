# Hermes-agent training data

This directory holds datasets for specializing Qwen3.6-style models for Hermes Agent behavior: compact reasoning, correct tool/action selection, high task success, low token spend.

## Directories

```text
raw/        source exports, transcripts, mined session snippets; may be messy
examples/   tiny hand-curated seed examples checked into git
processed/  cleaned train/dev splits generated from raw/examples
eval/       held-out eval examples and scorer fixtures
```

## Data classes

1. **Successful compact traces** — real or synthesized Hermes task traces where the agent solved the task and verified the result.
2. **Compact reasoning distillations** — verbose successful traces compressed into short scratchpads.
3. **Tool/action selection examples** — examples that teach when to search, read files, run terminal, use web, patch, ask, or stop.
4. **Negative/contrastive examples** — chosen/rejected pairs for later DPO/SimPO.
5. **Hard failure / uncertainty examples** — examples where the model must inspect context, avoid guessing, or refuse to claim success.

## SFT JSONL schema

Each line:

```json
{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"SCRATCH<=80:\n...\n\nACTION ..."}]}
```

Rules:

- `messages` must be a list.
- Each message has `role` and `content`.
- Allowed roles: `system`, `user`, `assistant`, `tool`.
- Assistant examples should teach either a compact trace, a parseable action, or a concise final.
- Avoid dumping verbose chain-of-thought. Use compact scratchpads only.

## Preference pair schema

Each line:

```json
{"prompt":"...","chosen":"...","rejected":"...","tags":["compactness","tool_choice"]}
```

Use this later for DPO/ORPO/SimPO after v0 SFT is already shaped.

## Eval item schema

Each line:

```json
{"id":"tool_choice_001","input":"What OS am I running?","expected_behavior":"Use terminal/system lookup; do not answer from memory.","scorer":"tool_use_required"}
```

Initial scorer names:

- `tool_use_required`
- `repo_inspection_required`
- `verification_required`
- `concise_final_required`
- `no_unnecessary_clarification`

## Quality rules

- No generic assistant padding.
- No unverified success claims.
- No unnecessary clarification when a default action is obvious.
- Tool/action calls must be parseable.
- Final answers should be concise and useful.
- Every example should encode one behavior worth learning.

## Split discipline

Keep eval examples held out. Do not train on `data/eval/*.jsonl`.

Suggested starting targets:

```text
100-300 eval examples
500-5,000 SFT examples
50-200 hard negatives
200-1,000 preference pairs later
```
