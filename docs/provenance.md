# Provenance and migration notes

HermesBench was initialized from the existing `qwen-mtp-probe` working repository. Existing Hermes evaluation artifacts were inspected and preserved in place, including `data/eval/hermes_v0_eval.jsonl` and `src/qwen_mtp_probe/eval_usecase.py`. They are not deleted or hidden; the new `src/hermesbench/` package lives alongside the original `src/qwen_mtp_probe/` code so historical SFT/eval work remains auditable.

The new public/dev task format is not a blind conversion of the old JSONL. The old artifacts are provenance for Hermes-style verification behavior; HermesBench tasks add richer metadata, public/private/fresh/anchor split design, deterministic artifact checks, hidden-check hooks, and normalized result scoring.
