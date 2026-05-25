# Qwen3.6 MTP probe

Minimal custom probe for deciding whether `Qwen3.6-35B-A3B` can be specialized while preserving/train-refreshing its MTP path.

## What this proves now

The lightweight metadata probe checks HF config + safetensor index without downloading the 35B model shards.

```bash
PYTHONPATH=src uv run --with torch python -m qwen_mtp_probe.probe \
  --metadata-only \
  --model unsloth/Qwen3.6-35B-A3B \
  --output reports/unsloth-qwen3.6-35b-a3b-metadata.json
```

Current result: `unsloth/Qwen3.6-35B-A3B` has `mtp_num_hidden_layers = 1` and 19 `mtp.*` tensors in the safetensor index.

## What the unit-tested utilities cover

- discover `mtp.*` parameters
- freeze everything except MTP modules
- compute normal next-token loss
- compute one or more future-token MTP auxiliary losses
- verify MTP logits receive gradients in a toy setting

```bash
uv run --with pytest --with torch python -m pytest tests/test_probe.py -q
```

## GPU feasibility gate

Run this on a GPU box with enough memory for the HF safetensors checkpoint:

```bash
PYTHONPATH=src uv run --with torch --with transformers --with accelerate python -m qwen_mtp_probe.probe \
  --model unsloth/Qwen3.6-35B-A3B \
  --output reports/unsloth-qwen3.6-35b-a3b-loaded.json
```

That verifies the loaded model exposes `mtp.*` parameters and can mark only those params trainable. The next custom trainer should add a real batch forward and backprop using:

```text
loss = next_token_ce + 0.05..0.1 * mtp_future_token_ce
```

Then inspect nonzero `mtp.*` gradient norms before any serious SFT/RL run.

## Hermes-agent specialization

This repo is also the working folder for Hermes-agent model specialization: compact reasoning traces, tool/action selection, SFT, optional preference/RL, and MTP refresh after behavior shifts.

See:

- `docs/HERMES_AGENT_SPECIALIZATION.md`
- `docs/plans/hermes-agent-v0-sft-main.md`

Current training target: maximize Hermes-agent task performance with the least necessary reasoning/token spend. The first behavior run should be `v0-sft-main`; MTP refresh comes after SFT changes the output distribution.
