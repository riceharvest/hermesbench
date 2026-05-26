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
{"messages":[{"role":"system","content":"..."},{"role":"user","content":"..."},{"role":"assistant","content":"ACTION terminal {\"command\":\"date\"}"}],"style":"hermes-ultra-compact-v0"}
```

Rules:

- `messages` must be a list.
- Each message has `role` and `content`.
- Allowed roles: `system`, `user`, `assistant`, `tool`.
- Assistant examples should teach either a parseable action or concise final.
- Avoid dumping verbose chain-of-thought. Use compact scratchpads only.

## Hermes ultra-compact v0 target

`v0-sft-main` trains toward GPT-5.5-ish terse agent behavior, not verbose CoT imitation:

1. **ACTION-only** when the next step is obvious.
2. **SCRATCH<=32** only when a short private decision note materially improves tool choice.
3. **FINAL-only** for direct answers after evidence is already known.
4. No `SCRATCH<=80`, long chain-of-thought, generic planning narration, or fake verification.

Valid assistant targets:

```text
ACTION terminal {"command":"uname -a && cat /etc/os-release"}
```

```text
SCRATCH<=32:
Need full early-exit log and docs.

ACTION web_search {"query":"SGLang MTP speculative Qwen mamba extra_buffer"}
```

Build the current processed seed set with:

```bash
uv run python scripts/build_hermes_train.py \
  --input data/examples/hermes_compact_traces.seed.jsonl \
  --input data/examples/hermes_compact_traces.v0.jsonl \
  --input data/examples/hermes_compact_traces.generated.repo_dev.jsonl \
  --input data/examples/hermes_compact_traces.generated.live_verification.jsonl \
  --input data/examples/hermes_compact_traces.generated.training_process.jsonl \
  --input data/examples/hermes_compact_traces.generated.wave2.repo_ops.jsonl \
  --input data/examples/hermes_compact_traces.generated.wave2.live_data.jsonl \
  --input data/examples/hermes_compact_traces.generated.wave2.training_eval.jsonl \
  --input data/examples/hermes_compact_traces.real_mined.v0.jsonl \
  --input data/examples/hermes_compact_traces.multi_turn.v0.jsonl \
  --output data/processed/hermes_v0_train.jsonl \
  --report reports/hermes-v0-train-quality.json \
  --min-examples 2250
```

## Preference pair schema

Each line:

```json
{"prompt":"...","chosen":"...","rejected":"...","tags":["compactness","tool_choice"]}
```

Use `data/examples/hermes_preference_pairs.v0.jsonl` for DPO/ORPO/SimPO after v0 SFT is already shaped. It currently contains 200 hard negatives covering verbose answers, fake verification, unnecessary clarification, mental math/live facts without tools, premature RL/router/serving work, ungrounded benchmarks, and secret leakage.

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
- `ultra_compact_style`

## Prediction/eval harness

Generate held-out predictions first, then score them:

```bash
PYTHONPATH=src uv run python scripts/run_hermes_predictions.py \
  --eval data/eval/hermes_v0_eval.jsonl \
  --output reports/hermes-v0-predictions.stub.jsonl \
  --provider stub \
  --model stub-ultra-compact

PYTHONPATH=src uv run python scripts/run_hermes_eval.py \
  --eval data/eval/hermes_v0_eval.jsonl \
  --predictions reports/hermes-v0-predictions.stub.jsonl \
  --output reports/hermes-v0-eval.stub.json
```

Prediction JSONL rows contain:

```json
{"id":"...","input":"...","output":"...","model":"...","provider":"...","latency_ms":1.2,"output_tokens":12}
```

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
