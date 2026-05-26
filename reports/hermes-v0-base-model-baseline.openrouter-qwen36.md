# Hermes v0 OpenRouter base-model baseline

Model: `qwen/qwen3.6-35b-a3b`
Provider: OpenRouter
Eval: `data/eval/hermes_v0_eval.jsonl` (300 held-out items)
Predictions: `reports/hermes-v0-predictions.openrouter-qwen36.jsonl`
Report: `reports/hermes-v0-eval.openrouter-qwen36.json`

## Result

```json
{
  "passed": 293,
  "total": 300,
  "failed": 7,
  "pass_rate": 0.9766666666666667,
  "by_scorer": {
    "tool_use_required": {"passed": 50, "total": 50},
    "repo_inspection_required": {"passed": 46, "total": 50},
    "verification_required": {"passed": 47, "total": 50},
    "concise_final_required": {"passed": 50, "total": 50},
    "no_unnecessary_clarification": {"passed": 50, "total": 50},
    "ultra_compact_style": {"passed": 50, "total": 50}
  }
}
```

## Usage / cost

```json
{
  "prompt_tokens": 68733,
  "output_tokens": 5766,
  "total_tokens": 74499,
  "cost_usd": 0.022742478,
  "cost_per_successful_task_usd": 0.00007761937883959044,
  "avg_latency_ms": 2829.756619716451
}
```

## Reasoning-high rerun

Command used `--reasoning-effort high --max-tokens 1024` with reasoning excluded from visible output. Because OpenRouter/Qwen sometimes hung or returned null visible content after spending the budget on hidden reasoning, the final run used `scripts/run_hermes_predictions_isolated.py` with per-item process timeouts.

Predictions: `reports/hermes-v0-predictions.openrouter-qwen36-reasoning-high.jsonl`
Report: `reports/hermes-v0-eval.openrouter-qwen36-reasoning-high.json`

```json
{
  "passed": 245,
  "total": 300,
  "failed": 55,
  "pass_rate": 0.8166666666666667,
  "by_scorer": {
    "tool_use_required": {"passed": 43, "total": 50},
    "repo_inspection_required": {"passed": 38, "total": 50},
    "verification_required": {"passed": 30, "total": 50},
    "concise_final_required": {"passed": 49, "total": 50},
    "no_unnecessary_clarification": {"passed": 50, "total": 50},
    "ultra_compact_style": {"passed": 35, "total": 50}
  }
}
```

```json
{
  "prompt_tokens": 66757,
  "output_tokens": 169984,
  "total_tokens": 236735,
  "cost_usd": 0.282463038,
  "avg_latency_ms": 13658.897425163208,
  "sentinels": {
    "OPENROUTER_TIMEOUT": 6,
    "OPENROUTER_NO_CONTENT": 87,
    "OPENROUTER_ERROR": 0
  }
}
```

Reasoning-high was worse for this ultra-compact eval: lower pass rate, ~12.4x cost, ~4.8x latency, and many hidden-reasoning/no-visible-content failures. Keep reasoning disabled for this baseline and use SFT to teach compact action/final behavior directly.

## Notes

- OpenRouter reasoning disabled with `"reasoning": {"effort":"none", "exclude": true}` is the better base-model baseline for this harness.
- `reasoning=high` is not just slower; it often spends the output budget on hidden reasoning and fails the visible ultra-compact contract.
- Remaining no-reasoning failures are concentrated in repo inspection and verification. Several are borderline scorer issues or tool-choice mismatches, but they are useful as v0 comparison points.
