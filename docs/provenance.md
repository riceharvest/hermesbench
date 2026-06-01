# Provenance and migration notes

HermesBench was initialized from the existing `qwen-mtp-probe` working repository. Existing Hermes evaluation artifacts were inspected and preserved in place, including `data/eval/hermes_v0_eval.jsonl`, legacy conversion/training scripts, and the `src/qwen_mtp_probe/` namespace. They are retained for auditability; they are not deleted or hidden.

The installable HermesBench package is `src/hermesbench/` only. The legacy `qwen_mtp_probe` namespace is source-tree research/provenance material and is intentionally excluded from the HermesBench wheel. Running old model-probing scripts from a checkout may require the optional `ml` dependency set (`torch`, `transformers`, `accelerate`, `safetensors`), but those packages are not needed for normal benchmark validation, mock/shell/Hermes CLI runs, scoring, or local API/storage work.

The public/dev task format is not a blind conversion of the old JSONL. The old artifacts are provenance for Hermes-style verification behavior; HermesBench tasks add richer metadata, public/private/fresh/anchor split design, deterministic artifact checks, hidden-check hooks, and normalized result scoring.

Current manifest counts are documented in `README.md`: 70 manifest entries total, including 55 public-dev tasks. Public private-holdout files are executable sample/template tasks; official private packs remain outside the repository.
