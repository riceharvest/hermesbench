# DeepSeek-V4 applicability to Hermes Qwen3.6 specialization

Sources checked:

- https://www.alphaxiv.org/abs/deepseek-v4
- https://www.alphaxiv.org/overview/deepseek-v4
- https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro
- https://openlm.ai/deepseek-v4/
- https://build.nvidia.com/deepseek-ai/deepseek-v4-pro/modelcard
- https://www.together.ai/blog/serving-deepseek-v4-why-million-token-context-is-an-inference-systems-problem
- https://fireworks.ai/blog/what-deepseek-v4-says-about-training-platforms

## Project state when reviewed

We are in `v0-sft-main` behavior shaping, not MTP refresh, serving tuning, or RL.

Current local evidence:

- active train: `6,579` `hermes-ultra-compact-v0` examples
- quality: `invalid_examples: []`, `max_scratch_words: 14`, `avg_scratch_words: 2.28`
- tests: `70 passed`
- best valid balanced smoke: `77/80` (`96.25%`) on 80 held-out items
- latest extra-hardening rerun was invalid/stalled; do not count it
- current issue: remaining failures are verification-action specificity and malformed-action avoidance

## DeepSeek-V4 techniques and whether to apply them

| Technique | Apply now? | Rationale for this repo |
|---|---:|---|
| Independent domain expert cultivation | Yes, adapted | This maps cleanly to separate behavior slices/adapters: repo ops, live verification, training/eval, concise final. We are already doing this at the data-slice level. Keep it explicit and measured. |
| Unified consolidation via on-policy distillation | Later | Useful after we have several strong slice-specific checkpoints or teachers. Too early before v0 SFT is stable. |
| Reasoning effort modes | Yes, adapted | DeepSeek treats reasoning effort as trained behavior. Our equivalent is `ACTION`-only / `SCRATCH<=32` / concise `FINAL:`. Add explicit mode tags or system variants only if eval shows mode confusion. |
| GRPO / RL domain expert training | Not yet | DeepSeek uses GRPO after SFT. For us, SFT still has visible failures, so RL would optimize unstable behavior. Defer until v0 SFT beats base and failures are interpretable. |
| Multi-teacher distillation | Later, useful | Use GPT-5.5/OpenRouter/strong-agent traces as teachers, but compress into Hermes ultra-compact targets. Never import verbose CoT directly. |
| MTP/speculative prediction | Later | DeepSeek keeps MTP as part of model design. For us, MTP feasibility is already proven; refresh after SFT because normal decode behavior is source of truth. |
| MoE router changes / anticipatory routing | No for v0 | DeepSeek-scale stability trick. Our LoRA path should avoid router training unless eval proves routing mismatch. Router changes are too destabilizing for v0. |
| Muon optimizer | Maybe later | Interesting for full/foundation-scale training. For LoRA smoke/full SFT, optimizer swap is lower priority than data/eval failures. Consider only after stable v0 if convergence/cost is poor. |
| FP4/FP8 quantization-aware training | No for current v0 | DeepSeek uses massive infra and mixed precision. Our current BF16 PEFT path is known-working; quantization experiments already created risk. Do not block v0. |
| CSA/HCA hybrid attention / million-token architecture | No | This is architecture+serving-stack co-design. We are specializing Qwen3.6, not pretraining a new long-context model. Revisit only for future architecture work. |
| Serving cache policy for long context | Later | Together's V4 analysis is relevant after v0 behavior works. It does not help current verification/tool-call failures. |

## Timeline impact

DeepSeek-V4 supports the current order rather than changing it:

1. Finish behavior SFT gate.
2. Run a valid hardened 60-step smoke with unique run artifacts/logging fixed.
3. If the smoke reaches about `79-80/80`, run longer/full `v0-sft-main` adapter training.
4. Compare checkpoint to base on the 300-item held-out eval and cost/tokens per pass.
5. Only then do `v0-sft-main-mtp-refresh`.
6. Then serving benchmark normal vs MTP.
7. Only after plateau: slice-specific RL/GRPO or preference optimization.
8. Optional later: consolidate multiple slice-specific adapters/teachers via distillation.

## Concrete next repo actions

1. Fix Modal run observability: unique report path/run id per launch, so stale `/reports/qwen36-hermes-v0-sft-smoke.json` cannot be mistaken for the latest run.
2. Rerun the 60-step hardened smoke once.
3. If still below target, patch the exact failure class again; otherwise graduate to longer v0 SFT.
4. Keep MTP work blocked until a normal-decode checkpoint passes behavior eval.
