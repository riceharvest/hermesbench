# Hermes Qwen3.6 Specialization Process Status

This is the canonical tracker for where the project is in the specialization pipeline. Update it whenever a stage gate is passed, blocked, or deliberately skipped.

## Current position

We are **past the MTP feasibility probe** and currently at **v0-sft-main preparation**.

The next real work is not another MTP probe, serving optimization, or RL. It is changing normal model behavior first: build enough ultra-compact Hermes training data and held-out behavior eval coverage to run `v0-sft-main` safely. Serving, MTP refresh, and throughput comparisons stay later.

## Stage tracker

| Stage | Status | Evidence | Next action |
|---|---|---|---|
| Probe: checkpoint metadata | Done | `reports/unsloth-qwen3.6-35b-a3b-metadata.json`, `reports/qwen-official-qwen3.6-35b-a3b-metadata.json` | No action unless model changes |
| Probe: stock HF MTP exposure | Done | `reports/modal-gradient-probe.json` | Treat stock HF as dropping `mtp.*` |
| Probe: manual MTP reconstruction | Done | `reports/modal-manual-mtp-probe.json` | Keep using `src/qwen_mtp_probe/qwen_mtp.py` |
| Probe: MTP-only overfit | Done | `reports/modal-mtp-overfit-probe.json` | No action unless training code changes materially |
| Probe: MTP refresh export | Done | `reports/modal-mtp-export-probe.json`, `reports/qwen36-mtp-refresh-export-manifest.json` | Reuse export pattern after real SFT |
| Probe: serving smoke | Done for SGLang, blocked for vLLM | `reports/modal-sglang-bench.json`, `reports/modal-vllm-bench-attempt.json` | Use SGLang as default serving path |
| v0-sft-main data | 6,432-example mixed compact set passed | `data/processed/hermes_v0_train.jsonl`, `data/examples/hermes_gpt55_teacher_sft.v0.jsonl`, `reports/hermes-v0-train-quality.json`, `scripts/build_hermes_train.py` | Ready for first SFT smoke run |
| v0-sft-main eval | 300 held-out items + OpenRouter baseline | `data/eval/hermes_v0_eval.jsonl`, `reports/hermes-v0-eval.openrouter-qwen36.json`, `scripts/run_hermes_predictions.py` | Compare SFT checkpoint against base-model baseline |
| v0-sft-main train | Not started | `src/qwen_mtp_probe/train_sft.py` dry-run only | Run only after data/eval gates pass |
| v0-mtp-refresh | Waiting on SFT | `docs/plans/hermes-agent-v0-mtp-refresh.md` | Refresh after `v0-sft-main` checkpoint exists |
| v0 benchmark | Waiting on SFT + MTP refresh | SGLang smoke only | Compare normal vs MTP on target prompts |
| v1 RL | Later | none | Do not start until SFT is clearly useful |
| v1 MTP refresh | Later | none | Refresh after RL if RL shifts output distribution |

## Proven MTP facts

- `unsloth/Qwen3.6-35B-A3B` has `mtp_num_hidden_layers = 1` and 19 `mtp.*` checkpoint tensors.
- Stock Transformers Qwen3.5/Qwen3.6 MoE loading ignores `^mtp.*`, so a normal HF load exposes 0 MTP parameters and forward outputs only `loss` and `logits`.
- Manual reconstruction using HF Qwen3.5 MoE blocks works:
  - `Qwen3_5MoeDecoderLayer`
  - `Qwen3_5MoeRMSNorm`
  - `nn.Linear(hidden_size * 2, hidden_size, bias=False)` for `mtp.fc`
  - one forced `full_attention` MTP decoder layer
  - shared base token embeddings and LM head
- All 19 checkpoint MTP tensors load with no missing or unexpected keys.
- All 19 reconstructed MTP tensors receive nonzero gradients.
- Tiny MTP-only overfit worked on 16 structured-output examples:
  - initial eval loss: `9.72265625`
  - final eval loss: `0.6064453125`
  - loss delta: `9.1162109375`
- Refreshed MTP export worked:
  - 19 tensors exported
  - reload max absolute diff: `0.0`
  - updated safetensors index repoints all `mtp.*` keys to `mtp-refresh.safetensors`
- SGLang can serve the assembled checkpoint in both normal and MTP speculative modes.

## Serving status

SGLang is the current working backend.

Single-H100 BF16 smoke result from `reports/modal-sglang-single-h100-bench.json`:

- GPU: Modal `H100` single GPU, `tp=1`
- serving config: `mem_fraction_static=0.88`, `max_total_tokens=4096`, `max_running_requests=1`, CUDA graphs enabled
- normal decode: `20.53 tok/s`
- speculative/EAGLE: `34.18 tok/s`
- speedup: about `1.67x`
- fit note: the first single-H100 attempt with `mem_fraction_static=0.70`, `max_total_tokens=8192`, `max_running_requests=4` loaded weights but failed scheduler pool init with `Not enough memory. Please try to increase --mem-fraction-static.`

Earlier dual-H100 smoke result from `reports/modal-sglang-bench.json`:

- GPU: Modal `H100:2`, `tp=2`
- normal decode: `10.50 tok/s`
- speculative/EAGLE: `20.01 tok/s`
- speedup: about `1.90x`

Interpretation: single-H100 locality is better for this tiny batch-1 smoke than the old dual-H100 TP=2 debug path. Still do not treat either as final production performance; they are short smoke tests over four compact JSON prompts.

Known-good speculative shape:

```bash
SGLANG_ENABLE_SPEC_V2=1 python -m sglang.launch_server \
  --model-path <assembled-checkpoint> \
  --reasoning-parser qwen3 \
  --speculative-algorithm EAGLE \
  --speculative-num-steps 3 \
  --speculative-eagle-topk 1 \
  --speculative-num-draft-tokens 4 \
  --mamba-scheduler-strategy extra_buffer
```

Small smoke result from `reports/modal-sglang-bench.json`:

- normal decode: `10.50 tok/s`
- speculative/EAGLE: `20.01 tok/s`
- speedup: about `1.90x`

Do not treat this as the final performance number. It is a smoke test, not a real target-prompt benchmark.

vLLM is not the default path right now. The Modal TP=2 H100 attempts loaded or began loading the checkpoint but stalled around post-load/shared-memory startup/profiling. Revisit only if SGLang fails a real requirement.

## Active plan

### 1. Finish v0-sft-main preparation

Objective: make normal-decode Hermes behavior better before spending effort on speculative acceleration or serving performance.

Behavior-first scope:

- Optimize output shape, tool choice, verification discipline, and concise finals.
- Use OpenRouter/OpenAI-compatible prediction runs only as cheap behavior baselines when useful.
- Do not spend time on local serving throughput, SGLang tuning, vLLM recovery, MTP accept rate, or GPU benchmark polish until after `v0-sft-main` changes behavior.

Required before training:

- Convert/minify successful Hermes-style traces into `data/processed/hermes_v0_train.jsonl`. Current processed data has 6,432 examples: 2,250 ultra-compact v0 examples plus 4,182 imported GPT-5.5 compact teacher traces accepted by maintainer decision.
- Prefer `ACTION`-only when obvious, `SCRATCH<=32` for ultra-compact v0 rows, and imported GPT-5.5 teacher traces may keep `SCRATCH<=96` by maintainer decision.
- Keep examples compact: action selection, tool discipline, verification, short final answers.
- Exclude verbose generic chat traces and failed/uncertain traces unless they are explicitly negative/preference examples.
- Expand evals beyond the seed items so the baseline and SFT checkpoint can be compared.
- Run local schema/eval tests.
- Run SFT dry-run and confirm no accidental model download in dry-run mode.

Primary files:

- `data/README.md`
- `data/examples/hermes_compact_traces.seed.jsonl`
- `data/examples/hermes_compact_traces.v0.jsonl`
- `data/examples/hermes_compact_traces.generated.repo_dev.jsonl`
- `data/examples/hermes_compact_traces.generated.live_verification.jsonl`
- `data/examples/hermes_compact_traces.generated.training_process.jsonl`
- `data/examples/hermes_compact_traces.generated.wave2.repo_ops.jsonl`
- `data/examples/hermes_compact_traces.generated.wave2.live_data.jsonl`
- `data/examples/hermes_compact_traces.generated.wave2.training_eval.jsonl`
- `data/examples/hermes_compact_traces.real_mined.v0.jsonl`
- `data/examples/hermes_compact_traces.multi_turn.v0.jsonl`
- `data/examples/hermes_gpt55_teacher_sft.v0.jsonl`
- `data/examples/hermes_preference_pairs.v0.jsonl`
- `data/processed/hermes_v0_train.jsonl`
- `reports/hermes-v0-train-quality.json`
- `data/eval/hermes_v0_eval.jsonl`
- `reports/hermes-v0-predictions.openrouter-qwen36.jsonl`
- `reports/hermes-v0-eval.openrouter-qwen36.json`
- `reports/hermes-v0-base-model-baseline.openrouter-qwen36.md`
- `data/eval/hermes_v0_eval.seed.jsonl`
- `src/qwen_mtp_probe/ultra_compact.py`
- `src/qwen_mtp_probe/prediction_runner.py`
- `src/qwen_mtp_probe/datasets.py`
- `src/qwen_mtp_probe/eval_usecase.py`
- `src/qwen_mtp_probe/train_sft.py`
- `scripts/run_hermes_eval.py`
- `configs/qwen36-hermes-v0-sft.yaml`

Gate to pass:

```bash
uv run --extra test python -m pytest
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
  --input data/examples/hermes_gpt55_teacher_sft.v0.jsonl \
  --output data/processed/hermes_v0_train.jsonl \
  --report reports/hermes-v0-train-quality.json \
  --min-examples 6432
PYTHONPATH=src uv run python scripts/run_hermes_eval.py \
  --eval data/eval/hermes_v0_eval.jsonl \
  --output reports/hermes-v0-baseline-template.json
PYTHONPATH=src uv run python scripts/run_hermes_predictions.py \
  --eval data/eval/hermes_v0_eval.jsonl \
  --output reports/hermes-v0-predictions.stub.jsonl \
  --provider stub \
  --model stub-ultra-compact
PYTHONPATH=src uv run python scripts/run_hermes_eval.py \
  --eval data/eval/hermes_v0_eval.jsonl \
  --predictions reports/hermes-v0-predictions.stub.jsonl \
  --output reports/hermes-v0-eval.stub.json
PYTHONPATH=src uv run python -m qwen_mtp_probe.train_sft \
  --config configs/qwen36-hermes-v0-sft.yaml \
  --dry-run
```

### 2. Run `v0-sft-main`

Objective: specialize normal decode first.

Rules:

- No RL in this stage.
- Do not train router initially.
- Prefer LoRA/DoRA targets on attention and expert MLP projections.
- Normal-decode quality is the source of truth.
- Measure task success, brevity/format compliance, and cost per successful task.

Output target:

```text
outputs/qwen36-hermes-v0-sft-main/
```

Gate to pass:

- SFT checkpoint beats base on Hermes eval cost per successful task.
- It does not regress basic instruction following or compact final answer behavior.
- If it fails quality, fix data/evals before touching MTP.

### 3. Later: run `v0-sft-main-mtp-refresh`

Objective: restore/improve speculative accept rate after SFT changes the output distribution. This is explicitly after behavior has moved; do not work this path during the behavior-first SFT loop.

Rules:

- Freeze the SFT/base behavior path and train MTP-only unless a specific eval shows this is insufficient.
- Use the manual MTP path if HF still ignores `mtp.*`.
- Export `mtp-refresh.safetensors` and an updated safetensors index.

Primary plan:

- `docs/plans/hermes-agent-v0-mtp-refresh.md`

Gate to pass:

- MTP refresh trains without missing/unexpected MTP tensors.
- Export reload diff is `0.0` or explained.
- Assembled checkpoint serves in SGLang normal and speculative modes.

### 4. Later: benchmark normal vs MTP

Objective: decide whether MTP matters for this use case after the behavior checkpoint exists. Do not optimize serving before we know the model behavior is worth serving.

Measure on target prompts, not smoke prompts:

- task success
- compactness / formatting
- normal decode tok/s
- MTP decode tok/s
- latency
- cost per successful task
- speculative accept behavior if exposed by backend

Decision rule:

- If MTP gives less than about `1.25x` improvement in cost per successful task, keep the SFT model but do not count MTP as a major advantage.
- If MTP harms quality or formatting, ship normal decode and revisit refresh data/alignment.

### 5. Later: v1 RL, then v1 MTP refresh

Only start RL after `v0-sft-main` is clearly useful and evals are reliable.

RL target:

- optimize task success/cost after SFT already knows the format and behavior
- avoid using RL to teach basic tool discipline or output shape

After RL, run another MTP refresh because RL can shift the output distribution again.

## Do-not-do list

- Do not redo the MTP probe unless base model, Transformers version, or serving backend changes.
- Do not start RL before SFT is useful.
- Do not train router initially; add router only if eval shows routing mismatch.
- Do not treat the SGLang smoke speedup as production performance.
- Do not optimize MTP at the expense of normal-decode quality.
- Do not let serving/backend work delay the behavior-first SFT loop.
