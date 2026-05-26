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

## Notes

- OpenRouter reasoning needed to be disabled with `"reasoning": {"effort":"none", "exclude": true}`; otherwise the provider returned reasoning with null final content and hit the output cap.
- Remaining failures are concentrated in repo inspection and verification. Several are borderline scorer issues or tool-choice mismatches, but they are useful as v0 comparison points.
