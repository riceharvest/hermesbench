# Hermes Agent v0 MTP Refresh Plan

**Goal:** Refresh Qwen3.6 MTP heads after `v0-sft-main` changes the Hermes-agent output distribution.

## Preconditions

- `v0-sft-main` beats baseline on cost per successful task.
- Normal decode quality is acceptable.
- Adapter/merged checkpoint exists.
- Eval report exists.

## Inputs

```text
outputs/qwen36-hermes-v0-sft-main/
data/processed/hermes_v0_train.jsonl
configs/qwen36-hermes-v0-sft.yaml
```

## Method

Use existing manual MTP module path from `src/qwen_mtp_probe/qwen_mtp.py` if HF still drops `mtp.*`.

Train MTP-only:

```text
loss = next_token_ce + mtp_weight * mtp_future_token_ce
mtp_weight = 0.05..0.1
num_speculative_tokens = 2
```

Export:

```text
mtp-refresh.safetensors
model.safetensors.index.with-mtp-refresh.json
```

Assemble a serving checkpoint with `scripts/assemble_mtp_refresh_checkpoint.py`.

## Serving eval

Normal SGLang:

```bash
python -m sglang.launch_server \
  --model-path <assembled-v0-checkpoint> \
  --reasoning-parser qwen3
```

MTP SGLang:

```bash
SGLANG_ENABLE_SPEC_V2=1 python -m sglang.launch_server \
  --model-path <assembled-v0-checkpoint> \
  --reasoning-parser qwen3 \
  --speculative-algorithm EAGLE \
  --speculative-num-steps 3 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 4 \
  --mamba-scheduler-strategy extra_buffer
```

## Decision rule

If MTP gives less than ~1.25x improvement in cost per successful task, keep the specialization but do not count MTP as a major advantage.
