# Hermes v0 base-model baseline deferred

Date: 2026-05-26

A real base-model behavior baseline was not run in this pass.

Reason:
- `scripts/run_hermes_predictions.py` delegates to `qwen_mtp_probe.prediction_runner`.
- `src/qwen_mtp_probe/prediction_runner.py` currently exposes only `--provider stub` and raises `NotImplementedError` for non-stub providers.
- The only SFT config found points at `unsloth/Qwen3.6-35B-A3B`, which would require remote/heavy model setup rather than a cheap local baseline.
- Existing stub prediction/eval artifacts already cover the deterministic harness path, but they are not a base-model behavior baseline.

Deferred until one of these exists:
- a cheap local model path/provider in the prediction runner;
- an OpenAI/OpenRouter-compatible provider with an explicit spend cap;
- a pre-running local inference endpoint suitable for the held-out Hermes eval.

No API calls or heavy model downloads were attempted.
