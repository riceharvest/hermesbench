# Hermes Qwen3.6 Specialization Process Status

This is the canonical tracker for where the project is in the specialization pipeline. Update it whenever a stage gate is passed, blocked, or deliberately skipped.

## Current position

We are **past the MTP feasibility probe** and currently in the **v0-sft-main behavior smoke loop**.

The next real work is not another MTP probe, serving optimization, or RL. It is changing normal model behavior first. The active train set is now the cleaned 6,542-row `hermes-ultra-compact-v0` set; verbose GPT-style teacher traces were removed from active SFT after a smoke run proved that loss can drop while behavior stays verbose. Serving, MTP refresh, and throughput comparisons stay later.

## Stage tracker

| Stage | Status | Evidence | Next action |
|---|---|---|---|
| Probe: checkpoint metadata | Done | `reports/unsloth-qwen3.6-35b-a3b-metadata.json`, `reports/qwen-official-qwen3.6-35b-a3b-metadata.json` | No action unless model changes |
| Probe: stock HF MTP exposure | Done | `reports/modal-gradient-probe.json` | Treat stock HF as dropping `mtp.*` |
| Probe: manual MTP reconstruction | Done | `reports/modal-manual-mtp-probe.json` | Keep using `src/qwen_mtp_probe/qwen_mtp.py` |
| Probe: MTP-only overfit | Done | `reports/modal-mtp-overfit-probe.json` | No action unless training code changes materially |
| Probe: MTP refresh export | Done | `reports/modal-mtp-export-probe.json`, `reports/qwen36-mtp-refresh-export-manifest.json` | Reuse export pattern after real SFT |
| Probe: serving smoke | Done for SGLang, blocked for vLLM | `reports/modal-sglang-bench.json`, `reports/modal-vllm-bench-attempt.json` | Use SGLang as default serving path |
| v0-sft-main data | 6,542-example ultra-compact set passed | `data/processed/hermes_v0_train.jsonl`, `reports/hermes-v0-train-quality.json`, `scripts/build_hermes_train.py` | Use active set for behavior smoke/full SFT |
| v0-sft-main eval | 300 held-out items + OpenRouter baseline | `data/eval/hermes_v0_eval.jsonl`, `reports/hermes-v0-eval.openrouter-qwen36.json`, `scripts/run_hermes_predictions.py` | Compare SFT checkpoint against base-model baseline |
| v0-sft-main train | Lightning RTXP_6000_X_2 60-step smoke passed 72/80 held-out items | `scripts/runpod_train_sft_smoke.py`, `reports/lightning/lightning-rtxpro2-60step-rerun-20260528T150621Z.json` | Harden verification-action examples/scorers, then rerun once; do not start MTP yet |
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

vLLM is not the default path right now. The Modal TP=2 H100 attempts loaded or began loading the checkpoint but stalled around post-load/shared-memory startup/profiling. Revisit only if SGLang fails a real requirement.

## SFT smoke status

Dual-H100 BF16 PEFT is the known-working 35B training path. Single 80GB attempts remain too tight for this trainer path; do not keep poking them without a materially different stack.

Important smoke lesson: the first cleaned-data smoke still used full-transcript labels, so the loss dropped but the model generated verbose `Here's a thinking process...`. The Modal trainer now masks labels to assistant target tokens only.

Assistant-only smoke result from `reports/modal/qwen36-hermes-v0-sft-smoke-assistant-only.json`:

- command: `modal run modal_train_sft.py --model-name unsloth/Qwen3.6-35B-A3B --max-steps 20 --max-seq-length 2048 --train-limit 1024 --grad-accum 16 --lora-r 16 --lora-alpha 32`
- GPU: Modal `H100:2`
- label masking: `assistant_only`
- optimizer steps: `20`; micro steps: `320`
- initial loss: `5.0293`; final loss: `1.5878`; loss delta: `3.4414`
- avg tokens: `72.51`; avg label tokens: `27.95`
- smoke generation: `ACTION terminal {"command":"date +%T"}`

Broader smoke result from `reports/modal/qwen36-hermes-v0-sft-smoke-40step-eval30.json`:

- command: `modal run modal_train_sft.py --model-name unsloth/Qwen3.6-35B-A3B --max-steps 40 --max-seq-length 2048 --train-limit 2048 --grad-accum 16 --lora-r 16 --lora-alpha 32 --eval-limit 30`
- GPU: Modal `H100:2`
- label masking: `assistant_only`
- optimizer steps: `40`; micro steps: `640`
- initial loss: `3.9447`; final loss: `3.4153`; tail losses are noisy because the examples are very short and heterogeneous
- held-out smoke eval: `30/30` passed task scorer + ultra-compact style scorer
- smoke generation: `ACTION terminal {"command":"date"}`
- contamination scan over the 30 outputs found 0 verbose reasoning markers and 0 blocked destructive command markers.

Broader balanced smoke result from `reports/modal/qwen36-hermes-v0-sft-smoke-60step-balanced.json`:

- command: `modal run modal_train_sft.py --model-name unsloth/Qwen3.6-35B-A3B --max-steps 60 --max-seq-length 2048 --max-train-tokens 512 --train-limit 4096 --grad-accum 16 --lora-r 16 --lora-alpha 32 --eval-limit 80`
- GPU: Modal `H100:2`
- label masking: `assistant_only`
- token filter: 4,047 tokenized rows before cap, 2,839 after dropping rows over 512 tokens
- optimizer steps: `60`; micro steps: `960`; elapsed: `1479.14s`
- initial loss: `1.0881`; final loss: `0.9576`; loss delta: `0.1305`; tail losses remain noisy because rows are short and heterogeneous
- held-out smoke eval: `75/80` passed task scorer + ultra-compact style scorer (`93.75%`)
- balanced scorer mix: tool use `14`, repo inspection `14`, verification `13`, concise final `13`, no-clarify `13`, ultra-compact style `13`
- smoke generation: `ACTION terminal {"command":"date -u"}`
- failures concentrate in `verification_required`: four premature `FINAL:` answers without evidence-gathering action, plus one terminal `grep` evidence action that exposed an eval-scorer gap fixed in `src/qwen_mtp_probe/eval_usecase.py`.

Verification-hardened balanced smoke result from `reports/modal/qwen36-hermes-v0-sft-smoke-60step-verification-hardened.json`:

- command: `modal run modal_train_sft.py --model-name unsloth/Qwen3.6-35B-A3B --max-steps 60 --max-seq-length 2048 --max-train-tokens 512 --train-limit 4096 --grad-accum 16 --lora-r 16 --lora-alpha 32 --eval-limit 80`
- GPU: Modal `H100:2`
- label masking: `assistant_only`
- token filter: 4,047 tokenized rows before cap, 2,887 after dropping rows over 512 tokens
- optimizer steps: `60`; micro steps: `960`; elapsed: `1310.93s`
- initial loss: `4.4263`; final loss: `0.3136`; loss delta: `4.1126`; tail losses remain noisy because rows are short and heterogeneous
- held-out smoke eval: `77/80` passed task scorer + ultra-compact style scorer (`96.25%`), improving from `75/80`
- balanced scorer mix: tool use `14`, repo inspection `14`, verification `13`, concise final `13`, no-clarify `13`, ultra-compact style `13`
- smoke generation: `ACTION terminal {"command":"date -u"}`
- remaining failures: one verification prompt still asks to verify rather than taking action (`FINAL: No. I need to verify...`), one verification prompt chooses weak `ls -la data/`, and one concise-final prompt emits a malformed/truncated terminal action. Patch these before calling v0 SFT behavior ready.

Lightning RTXP_6000_X_2 smoke result from `reports/lightning/lightning-rtxpro2-60step-rerun-20260528T150621Z.json`:

- command: `PYTHONPATH=src uv run python scripts/runpod_train_sft_smoke.py --max-steps 60 --max-seq-length 2048 --max-train-tokens 512 --train-limit 4096 --grad-accum 16 --lora-r 16 --lora-alpha 32 --eval-limit 80`
- GPU: Lightning AI `RTXP_6000_X_2`, 2x NVIDIA RTX PRO 6000 Blackwell Server Edition, ~97.9GB VRAM each
- label masking: `assistant_only`
- token filter: 4,047 tokenized rows before cap, 2,915 after dropping rows over 512 tokens
- optimizer steps: `60`; micro steps: `960`; elapsed: `1241.26s`
- initial loss: `1.7021`; final loss: `0.1651`; loss delta: `1.5371`
- held-out smoke eval: `72/80` passed task scorer + ultra-compact style scorer (`90.00%`)
- smoke generation: `ACTION terminal {"command":"date"}`
- remaining failures: seven verification prompts still produce premature `FINAL:`/non-evidence answers, and one concise-final prompt emits a malformed/truncated terminal action.

Interpretation: Lightning worked as a viable free/credit-backed GPU path and the model is trainable on 2x RTX PRO 6000, but this rerun regressed from the best Modal smoke score (`77/80`). Do not start MTP refresh or RL yet. The next gate is narrower: add targeted verification-action and malformed-action hardening, then rerun one balanced 60-step smoke.

DeepSeek-V4 applicability note: see `docs/DEEPSEEK_V4_APPLICABILITY.md`. The short version is that V4 supports our current sequence: specialist behavior cultivation first, optional consolidation/distillation later, MTP/serving after normal behavior works, and RL/GRPO only after SFT is useful. V4 architecture-scale features like CSA/HCA, mHC, FP4 QAT, Muon, and router interventions are not v0 blockers for this Qwen LoRA specialization.

## Active plan

### 1. Finish v0-sft-main preparation

Objective: make normal-decode Hermes behavior better before spending effort on speculative acceleration or serving performance.

Behavior-first scope:

- Optimize output shape, tool choice, verification discipline, and concise finals.
- Use OpenRouter/OpenAI-compatible prediction runs only as cheap behavior baselines when useful.
- Do not spend time on local serving throughput, SGLang tuning, vLLM recovery, MTP accept rate, or GPU benchmark polish until after `v0-sft-main` changes behavior.

Required before training:

- Convert/minify successful Hermes-style traces into `data/processed/hermes_v0_train.jsonl`. Current active processed data has 6,542 `hermes-ultra-compact-v0` examples, including a verification-hardening slice added after the 60-step balanced smoke exposed premature `FINAL:` answers on verification prompts. GPT-style compact teacher traces are kept as source material but excluded from active SFT until they can be proven not to reintroduce verbose reasoning.
- Prefer `ACTION`-only when obvious and `SCRATCH<=32` only when a small amount of reasoning is needed.
- Keep examples compact: action selection, tool discipline, verification, short final answers.
- Exclude verbose generic chat traces and failed/uncertain traces unless they are explicitly negative/preference examples.
- Expand evals beyond the seed items so the baseline and SFT checkpoint can be compared.
- Run local schema/eval tests.
- Run SFT dry-run and confirm no accidental model download in dry-run mode.

Primary files:

- `data/README.md`
- `data/examples/hermes_compact_traces.seed.jsonl`
- `data/examples/hermes_compact_traces.v0.jsonl`
- `data/examples/hermes_compact_traces.verification_hardening.v0.jsonl`
- `data/examples/hermes_compact_traces.generated.repo_dev.jsonl`
- `data/examples/hermes_compact_traces.generated.live_verification.jsonl`
- `data/examples/hermes_compact_traces.generated.training_process.jsonl`
- `data/examples/hermes_compact_traces.generated.wave2.repo_ops.jsonl`
- `data/examples/hermes_compact_traces.generated.wave2.live_data.jsonl`
- `data/examples/hermes_compact_traces.generated.wave2.training_eval.jsonl`
- `data/examples/hermes_compact_traces.real_mined.v0.jsonl`
- `data/examples/hermes_compact_traces.multi_turn.v0.jsonl`
- `data/examples/hermes_hf_openhands_swe.v0.jsonl`
- `data/examples/hermes_hf_openthoughts_terminal.v0.jsonl`
- `data/examples/hermes_gpt55_teacher_sft.v0.jsonl`
- `data/raw/hf/hermes_hf_toolcall_source_ready.v0.jsonl`
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
  --input data/examples/hermes_compact_traces.verification_hardening.v0.jsonl \
  --input data/examples/hermes_compact_traces.generated.repo_dev.jsonl \
  --input data/examples/hermes_compact_traces.generated.live_verification.jsonl \
  --input data/examples/hermes_compact_traces.generated.training_process.jsonl \
  --input data/examples/hermes_compact_traces.generated.wave2.repo_ops.jsonl \
  --input data/examples/hermes_compact_traces.generated.wave2.live_data.jsonl \
  --input data/examples/hermes_compact_traces.generated.wave2.training_eval.jsonl \
  --input data/examples/hermes_compact_traces.real_mined.v0.jsonl \
  --input data/examples/hermes_compact_traces.multi_turn.v0.jsonl \
  --input data/examples/hermes_hf_openhands_swe.v0.jsonl \
  --input data/examples/hermes_hf_openthoughts_terminal.v0.jsonl \
  --input data/examples/hermes_gpt55_teacher_sft.v0.jsonl \
  --output data/processed/hermes_v0_train.jsonl \
  --report reports/hermes-v0-train-quality.json \
  --min-examples 6542
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
