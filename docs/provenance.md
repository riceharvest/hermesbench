# Provenance and migration notes

HermesBench was initialized from the `qwen-mtp-probe` working repository. Existing Hermes evaluation artifacts were preserved in place, including `data/eval/hermes_v0_eval.jsonl`, legacy conversion/training scripts, and the `src/qwen_mtp_probe/` namespace. They are retained for auditability.

The installable HermesBench package is `src/hermesbench/` only. The legacy `qwen_mtp_probe` namespace is source-tree research/provenance material and is excluded from the HermesBench wheel. Running old model-probing scripts from a checkout may require the optional `ml` dependency set (`torch`, `transformers`, `accelerate`, `safetensors`), but those packages are not needed for normal benchmark validation, mock/shell/Hermes CLI runs, scoring, or local API/storage work.

The task format has pivoted from correctness-based ProjectOps validation to a telemetry-based minimum-capable-model probe. The current `natural-tools-dev` suite consists of 5 tasks designed to trace tool class usage directly.
