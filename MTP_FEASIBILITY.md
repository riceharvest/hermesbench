# Qwen3.6 MTP feasibility findings

## Root cause

Stock Hugging Face Transformers does **not** instantiate Qwen3.6/Qwen3.5 MoE MTP modules.

Evidence from `transformers.models.qwen3_5_moe.modeling_qwen3_5_moe`:

```python
_keys_to_ignore_on_load_unexpected = [r"^mtp.*"]
```

The first Modal probe confirmed this in practice:

- checkpoint safetensor index has 19 `mtp.*` tensors
- loaded HF model has 0 `mtp` parameters
- forward output keys are only `loss`, `logits`

Report: `reports/modal-gradient-probe.json`

## Feasibility result

Manual MTP reconstruction is possible.

Second Modal probe rebuilt an HF-native MTP module from Transformers Qwen3.5 MoE building blocks:

- `Qwen3_5MoeDecoderLayer`
- `Qwen3_5MoeRMSNorm`
- `nn.Linear(hidden_size * 2, hidden_size, bias=False)` for `mtp.fc`
- one forced `full_attention` decoder layer
- base model token embeddings and LM head are shared, matching `mtp_use_dedicated_embeddings=false` behavior

It then manually loaded the checkpoint `mtp.*` tensors from the safetensor shards.

Pass evidence from `reports/modal-manual-mtp-probe.json`:

```json
{
  "loaded_mtp_tensor_count": 19,
  "load_missing": [],
  "load_unexpected": [],
  "loss_requires_grad": true,
  "nonzero_mtp_grad_count": 19,
  "mtp_loss": 7.59375
}
```

All 19 reconstructed MTP tensors received nonzero gradients.

## MTP-only overfit result

The manual module has now been moved into reusable package code at `src/qwen_mtp_probe/qwen_mtp.py`, including:

- `ManualQwenMTP`
- checkpoint `mtp.*` shard loading with prefix stripping
- base-freeze / MTP-only trainability helper
- text-only rotary position setup
- 4D additive causal+padding mask generation
- depth-2 future-token CE helper

A third Modal run used that package code, loaded all 19 MTP tensors, trained only MTP parameters on 16 tiny structured-output examples, and verified overfit with the causal mask path enabled.

Report: `reports/modal-mtp-overfit-probe.json`

```json
{
  "loaded_mtp_tensor_count": 19,
  "load_missing": [],
  "load_unexpected": [],
  "trainable_mtp_param_count": 19,
  "last_nonzero_mtp_grad_count": 19,
  "example_count": 16,
  "steps": 24,
  "initial_eval_loss": 9.72265625,
  "final_eval_loss": 0.6064453125,
  "loss_delta": 9.1162109375
}
```

Modal run:

```text
https://modal.com/apps/myappleiddarimaan/main/ap-Ts7nRL2HubbFHHQeoKUtNY
```

Local tests:

```text
14 passed
```

## Remaining caveats

- Base hidden states are detached intentionally, because this path targets an MTP-only refresh after main SFT/RL.
- The mask is now a proper eager 4D causal+padding mask, but still should be parity-checked against the exact Transformers internal mask path before long training.
- The MTP loss uses one depth-2 CE head. Verify exact Qwen/vLLM speculative-step alignment before training multiple speculative tokens.
- This proves trainability, tensor compatibility, and tiny-set overfit. It still does **not** prove post-refresh MTP acceptance rate or serving tok/s.

## Export result

A fourth Modal run exported the refreshed MTP block as a serving-assembly artifact.

Report: `reports/modal-mtp-export-probe.json`

Modal run:

```text
https://modal.com/apps/myappleiddarimaan/main/ap-Me5iqMn4oqIfbY0mCPOJhd
```

Volume artifact:

```text
qwen-mtp-probe-results/qwen36-mtp-refresh-export/
├── mtp-refresh.safetensors                         # 1.6 GiB, 19 refreshed mtp.* tensors
├── model.safetensors.index.with-mtp-refresh.json   # original index, mtp.* keys repointed
└── manifest.json
```

Verification:

```json
{
  "exported_mtp_tensor_count": 19,
  "export_reload_max_abs_diff": 0.0,
  "mtp_key_count_in_updated_index": 19,
  "mtp_shards_in_updated_index": ["mtp-refresh.safetensors"]
}
```

Local helper for assembling a full local checkpoint dir:

```text
scripts/assemble_mtp_refresh_checkpoint.py
```

Usage shape:

```bash
python scripts/assemble_mtp_refresh_checkpoint.py \
  --source /path/to/original/hf/snapshot \
  --export /path/to/qwen36-mtp-refresh-export \
  --output /path/to/qwen36-mtp-refresh-checkpoint
```

## vLLM serving attempt

A first vLLM 0.21.0 TP=2 H100 Modal benchmark script was added at:

```text
modal_vllm_bench.py
```

It assembles the refreshed checkpoint from the original snapshot + exported MTP shard and tries both normal and speculative MTP decode.

Observed status:

- vLLM recognized the assembled checkpoint as `Qwen3_5MoeForConditionalGeneration`.
- Text-only mode was enabled with `limit_mm_per_prompt={"image": 0, "video": 0}`.
- The 27-shard assembled checkpoint began loading on TP=2 H100.
- First attempt loaded all shards, then hung in post-load/shared-memory broadcast/profiling.
- Second attempt added `NCCL_P2P_DISABLE=1`, `disable_custom_all_reduce=True`, `mm_processor_cache_gb=0`, and `mm_encoder_tp_mode="data"`; it still stalled around shard loading/post-load startup, so it was killed to avoid wasting GPU time.

## SGLang serving attempt

SGLang got further than vLLM on Modal H100:2.

Script:

```text
modal_sglang_bench.py
```

Fixes needed:

- First SGLang image missed `libnuma.so.1`; adding `apt_install("libnuma1")` fixed `sgl_kernel` import.
- The first readiness loop accidentally hammered `/health` because each 503 generated an immediately readable log line; the loop now uses a background log reader and throttled health polling.
- `--max-total-tokens 8192` was added to keep debug startup smaller.
- The benchmark client now sends `chat_template_kwargs={"enable_thinking": false}` plus `separate_reasoning=true`, and falls back to `reasoning_content` if `message.content` is empty.
- SGLang MTP is enabled with `--speculative-algorithm EAGLE`, not vLLM-style `NEXTN`.
- Qwen3.5/Qwen3.6 Mamba-MoE speculative serving needs `SGLANG_ENABLE_SPEC_V2=1` and `--mamba-scheduler-strategy extra_buffer`; otherwise SGLang exits with `Speculative decoding ... is not compatible with radix cache when using --mamba-scheduler-strategy no_buffer`.

Observed normal-decode result:

```json
{
  "ready_signal": "health",
  "mode": "normal",
  "generated_tokens": 103,
  "load_seconds": 450.6239776611328,
  "wall_seconds": 9.80680775642395,
  "tokens_per_second": 10.502908036769645
}
```

Observed speculative MTP result:

```json
{
  "ready_signal": "health",
  "mode": "nextn",
  "speculative_algorithm": "EAGLE",
  "speculative_minimal": false,
  "speculative_moe_runner_backend": null,
  "generated_tokens": 116,
  "load_seconds": 129.34748148918152,
  "wall_seconds": 5.798046112060547,
  "tokens_per_second": 20.006739815109054
}
```

The current small-prompt smoke benchmark shows about `1.90x` speculative speedup (`20.01 tok/s` vs `10.50 tok/s`) with non-empty compact JSON outputs in both modes.

Local report:

```text
reports/modal-sglang-bench.json
```

Local failure note:

```text
reports/modal-vllm-bench-attempt.json
```

Interpretation: vLLM still looks like a Modal/vLLM multi-GPU startup issue, but SGLang can now serve the assembled refreshed checkpoint in both normal and MTP speculative modes. The exported MTP tensors are usable by SGLang.

## Next implementation path

1. Run a larger benchmark sweep (`bench_speculative.py`-style) over realistic batch sizes and prompt lengths; tune `--speculative-num-steps`, `--speculative-eagle-topk`, and `--speculative-num-draft-tokens`.
2. Test `--speculative-moe-runner-backend triton` only if the default MoE runner becomes unstable or slower on larger batches; the first successful MTP smoke did not need it.
3. Measure acceptance rate / tok-s / latency / output quality / cost per successful task on real target prompts, not just four compact JSON smoke prompts.
4. Decide deployment backend: SGLang is now the working path; vLLM can be revisited separately with Docker `--ipc=host` or an environment that avoids the Modal shared-memory startup hang.
5. If acceptance and quality survive the larger sweep, fold this into the real SFT pipeline as `base -> main SFT -> MTP refresh -> SGLang EAGLE/MTP serving`.
