# Hermes-agent specialization target

This repository is now the working folder for specializing Qwen3.6-style open-weight models for **Hermes Agent performance**: high task success with the least necessary reasoning and token spend.

## Goal

Train a model/checkpoint that is optimized for Hermes-agent style work:

- follow user intent with minimal back-and-forth;
- choose the right tool/action quickly;
- keep internal reasoning compact;
- emit parseable, low-token action traces when traces are needed;
- avoid verbose generic assistant reasoning;
- preserve enough general coding/research ability for real tasks;
- maximize **successful tasks per dollar**, not raw benchmark score.

Target behavior is closer to a disciplined coding/research agent than a chat model.

## Current working repo

```text
/home/dario/Documents/dev workspace/qwen-mtp-probe
```

Existing work already proves the MTP path can be inspected, trained, exported, assembled, and served through SGLang. The next phase is main behavior specialization for Hermes-agent traces.

## Model/version naming

Keep versions explicit:

```text
base-qwen3.6-35b-a3b
v0-probe
v0-sft-main
v0-sft-mtp
v1-rl
v1-rl-mtp
```

Meaning:

- `base-qwen3.6-35b-a3b`: original base/instruct checkpoint.
- `v0-probe`: loader/trainability/eval harness sanity checks.
- `v0-sft-main`: first real Hermes-agent behavior SFT/LoRA/DoRA run.
- `v0-sft-mtp`: short MTP refresh after v0 SFT changes the output distribution.
- `v1-rl`: optional preference/RL stage only after SFT is boringly good.
- `v1-rl-mtp`: MTP refresh after the RL distribution shift.

## Performance objective

Primary metric:

```text
cost per successful Hermes task
```

Secondary metrics:

```text
quality score
invalid / unparsable output rate
tool/action correctness
tokens per successful task
visible output tokens
compact reasoning tokens / trace length
wall-clock latency
tok/s
MTP acceptance rate if exposed
regression rate on held-out general tasks
```

Raw tok/s is not enough. MTP is useful only if it improves successful task throughput on the target prompt distribution.

## Training data we want

We have some very compact reasoning traces already and can generate more. These are high-value because they directly encode the desired behavior: shortest useful scratchpad, decisive tool use, no generic explanation bloat.

Useful trace shape:

```text
OBSERVE: relevant user request + state + available tools
SCRATCH<=80: compact private reasoning / plan / constraint summary
ACTION: parseable tool/action call or final response
RESULT: tool result summary when applicable
FINAL: concise user-facing answer, if task complete
```

For training, convert this into chat or structured JSONL while preserving the compactness pressure.

## Dataset classes

### 1. Successful Hermes task traces

Use completed sessions where the agent actually solved something. Keep:

- user goal;
- key observations;
- compact reasoning trace;
- tool/action choices;
- final answer;
- verification evidence.

Drop or compress:

- tool spam;
- repeated logs;
- unrelated side conversations;
- huge raw outputs that do not affect decisions.

### 2. Compact reasoning distillations

Use larger models or human edits to rewrite verbose successful traces into compact traces.

Target examples:

```text
SCRATCH<=80:
Need confirm existing repo. qwen-mtp-probe has MTP proof; add SFT docs there, not new repo. Plan: eval -> SFT -> MTP refresh -> optional RL.

ACTION write_file {"path":"docs/HERMES_AGENT_SPECIALIZATION.md"}
```

Good compact traces mention constraints and next action, not a full essay.

### 3. Tool/action selection examples

Train choosing the right action:

- search/read before editing;
- use terminal for current system facts/math/git;
- use web for current docs;
- avoid asking when the default action is obvious;
- avoid running dangerous/public side effects without explicit scope.

### 4. Negative and contrastive examples

Important for preference tuning later. Keep pairs such as:

- compact correct trace vs verbose wandering trace;
- correct tool call vs plausible wrong tool call;
- verified answer vs unverified claim;
- asks unnecessary clarification vs acts on obvious default;
- over-reasons vs minimal adequate scratchpad;
- bloated final response vs concise useful final.

### 5. Hard failures

Keep examples where the model should:

- say it lacks context;
- inspect files/session history first;
- refuse to claim success without verification;
- avoid external side effects;
- stop after repeated failed fix attempts and re-investigate.

## Candidate JSONL formats

### SFT chat format

```json
{"messages":[{"role":"system","content":"You are Hermes Agent. Use compact reasoning and tool actions."},{"role":"user","content":"Need debug failing qwen MTP serving"},{"role":"assistant","content":"SCRATCH<=80:\nNeed inspect logs before changing flags. Search docs and run modal bench; root cause likely SGLang MTP flag/cache mode.\n\nACTION web_search {\"query\":\"SGLang MTP speculative qwen mamba scheduler no_buffer\"}"}]}
```

### Preference pair format

```json
{"prompt":"User asks what next after SFT plan","chosen":"Concise plan: eval -> SFT -> measure -> MTP refresh; no RL yet.","rejected":"Long generic fine-tuning taxonomy with no reference to current repo or collected findings."}
```

### Eval item format

```json
{"id":"tool_choice_001","input":"What OS am I running?","expected_behavior":"Use terminal/date/system lookup, do not answer from memory.","scorer":"tool_use_required"}
```

## Evaluation gates

Before training:

- Create held-out eval set first.
- Include exact pass/fail checks where possible.
- Record baseline from base model / current provider.

Minimum v0 gates:

```text
100-300 held-out examples
valid action/schema rate
correct tool-choice rate
compact trace length distribution
final-answer usefulness score
latency and token count
```

Do not call a training run successful unless it beats baseline on cost per successful task.

## Main training route

Preferred route for this project:

```text
HF Transformers + Accelerate custom trainer
→ PEFT LoRA/DoRA for v0
→ eval
→ custom MTP auxiliary refresh
→ SGLang/vLLM eval
→ optional DPO/GRPO later
→ MTP refresh after each major behavior shift
```

Unsloth Studio can be useful for fast/no-code experiments, but for Qwen3.6 + MTP we need custom control because stock HF may drop `mtp.*` tensors and Studio may not train or preserve MTP heads. The custom path is less opaque.

## Stage plan summary

### Stage 0 — dataset/eval contract

Define the exact Hermes-agent target contract:

- input shape;
- output/action shape;
- allowed tools/actions;
- compact reasoning budget;
- success criteria;
- forbidden behaviors.

### Stage 1 — v0 SFT main

Train LoRA/DoRA/QLoRA on compact successful Hermes-agent traces.

Focus:

- task completion;
- compact reasoning;
- correct tool choice;
- minimal user-facing output;
- no fake verification.

### Stage 2 — v0 eval

Measure against baseline:

```text
quality score
tokens/output
wall-clock latency
tool/action correctness
invalid output rate
cost/successful task
```

### Stage 3 — v0 MTP refresh

After SFT changes the output distribution, refresh MTP with explicit future-token auxiliary loss.

Known MTP recipe from this repo:

```text
loss = next_token_ce + mtp_weight * mtp_future_token_ce
mtp_weight = 0.05..0.1
num_speculative_tokens = 2
```

### Stage 4 — serving eval

Serve both normal and MTP/speculative modes:

```bash
vllm serve Qwen3.6-usecase-v0 \
  --reasoning-parser qwen3
```

```bash
vllm serve Qwen3.6-usecase-v0 \
  --reasoning-parser qwen3 \
  --speculative-config '{"method":"qwen3_next_mtp","num_speculative_tokens":2}'
```

SGLang working path from current repo:

```bash
SGLANG_ENABLE_SPEC_V2=1 python -m sglang.launch_server \
  --model-path Qwen3.6-usecase-v0 \
  --reasoning-parser qwen3 \
  --speculative-algorithm EAGLE \
  --speculative-num-steps 3 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 4 \
  --mamba-scheduler-strategy extra_buffer
```

If MTP gives less than ~1.25x real improvement on successful tasks, do not overvalue it. The specialization can still be worth it, just not because of MTP.

### Stage 5 — only then consider RL

Do not touch RL until v0 SFT is boringly good.

Good RL targets:

- fewer invalid outputs;
- better tool/action selection;
- fewer tokens;
- higher task success;
- better refusal/uncertainty calibration.

Options:

- DPO if we have chosen/rejected pairs;
- GRPO if we have a programmatic reward;
- rejection sampling + SFT if we want cheap/simple.

After RL:

```text
v1-rl
→ v1-rl-mtp-refresh
```

RL shifts output distribution, so MTP needs refresh again.

## Current evidence already collected

See `MTP_FEASIBILITY.md` for the full MTP details. Short version:

- `unsloth/Qwen3.6-35B-A3B` has `mtp_num_hidden_layers = 1` and 19 `mtp.*` tensors.
- Stock HF Transformers can ignore/drop `mtp.*` tensors.
- Manual MTP reconstruction loaded all 19 tensors.
- MTP-only overfit probe dropped eval loss from `9.72` to `0.61` on a tiny structured set.
- Export probe wrote `mtp-refresh.safetensors` and updated the safetensors index.
- vLLM TP=2 on Modal loaded/recognized the model but stalled around post-load/shared-memory startup.
- SGLang normal serving works.
- SGLang MTP serving works with `EAGLE`, `SGLANG_ENABLE_SPEC_V2=1`, and `--mamba-scheduler-strategy extra_buffer`.
- Smoke benchmark showed ~1.90x tok/s improvement on four compact JSON prompts.

## Immediate next deliverables

1. Create `data/README.md` with dataset conventions.
2. Add a tiny `data/examples/` seed set from compact Hermes traces.
3. Add `configs/qwen36-hermes-v0-sft.yaml` for v0 SFT intent.
4. Add `docs/plans/hermes-agent-v0-sft-main.md` as the implementation plan.
5. Then implement `src/qwen_mtp_probe/datasets.py` and `src/qwen_mtp_probe/eval_usecase.py` before any expensive training run.
