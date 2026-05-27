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

Status: **complete**. Do not rerun unless the base model, Transformers version, or serving backend changes.

The original stock-HF probe showed that Transformers ignores `^mtp.*`: the checkpoint index has 19 `mtp.*` tensors, but the loaded HF model exposes 0 MTP parameters and forward outputs only `loss` and `logits`.

The working path is the manual MTP module in `src/qwen_mtp_probe/qwen_mtp.py`. Modal probes proved:

- all 19 MTP tensors load with no missing/unexpected keys
- all 19 reconstructed MTP tensors receive nonzero gradients
- MTP-only tiny overfit works: eval loss `9.72 -> 0.606`
- refreshed MTP export reloads with max absolute diff `0.0`
- SGLang can serve the assembled checkpoint in normal and MTP speculative/EAGLE modes

See:

- `MTP_FEASIBILITY.md`
- `docs/PROCESS_STATUS.md`
- `reports/modal-manual-mtp-probe.json`
- `reports/modal-mtp-overfit-probe.json`
- `reports/modal-mtp-export-probe.json`
- `reports/modal-sglang-bench.json`

## Hermes-agent specialization

This repo is also the working folder for Hermes-agent model specialization: compact reasoning traces, tool/action selection, SFT, optional preference/RL, and MTP refresh after behavior shifts.

See:

- `docs/PROCESS_STATUS.md` — canonical current-stage tracker
- `docs/HERMES_AGENT_SPECIALIZATION.md`
- `docs/plans/hermes-agent-v0-sft-main.md`
- `docs/plans/hermes-agent-v0-mtp-refresh.md`

Current training target: maximize Hermes-agent task performance with the least necessary reasoning/token spend. We are currently at `v0-sft-main` preparation with a passing 6,432-row mixed compact SFT set: ultra-compact v0 rows plus GPT-5.5 compact teacher traces capped at `SCRATCH<=96`. The first behavior run should be `v0-sft-main`; MTP refresh comes after SFT changes the output distribution.
