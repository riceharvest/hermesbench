from __future__ import annotations

import argparse
import json
from pathlib import Path

from qwen_mtp_probe.datasets import load_eval_jsonl
from qwen_mtp_probe.eval_usecase import score_output, summarize_scores


def main() -> None:
    parser = argparse.ArgumentParser(description='Run deterministic Hermes-agent eval scaffold.')
    parser.add_argument('--eval', required=True, help='Eval JSONL path')
    parser.add_argument('--output', required=True, help='Report JSON path')
    parser.add_argument(
        '--predictions',
        help='Optional JSONL with {"id": ..., "output": ...}. Missing predictions are scored as empty.',
    )
    args = parser.parse_args()

    items = load_eval_jsonl(args.eval)
    predictions: dict[str, str] = {}
    prediction_rows: list[dict] = []
    if args.predictions:
        for line in Path(args.predictions).read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            prediction_rows.append(row)
            predictions[str(row['id'])] = str(row.get('output', ''))

    scored = []
    for item in items:
        output = predictions.get(item.id, '')
        result = score_output(item.scorer, output)
        scored.append(result)

    passed = sum(result.passed for result in scored)
    total_cost = sum(float(row.get('cost') or 0) for row in prediction_rows)
    report = {
        'run_name': 'baseline-template' if not args.predictions else Path(args.predictions).stem,
        'model': prediction_rows[0].get('model') if prediction_rows else None,
        'eval_path': args.eval,
        'prediction_path': args.predictions,
        'items': len(items),
        'scores': summarize_scores(scored),
        'latency': {
            'avg_ms': sum(float(row.get('latency_ms') or 0) for row in prediction_rows) / len(prediction_rows)
            if prediction_rows
            else None,
        },
        'tokens': {
            'prompt_tokens': sum(int(row.get('prompt_tokens') or 0) for row in prediction_rows),
            'output_tokens': sum(int(row.get('output_tokens') or 0) for row in prediction_rows),
            'reasoning_tokens': sum(int(row.get('reasoning_tokens') or 0) for row in prediction_rows),
            'visible_output_tokens_estimate': sum(
                max(int(row.get('output_tokens') or 0) - int(row.get('reasoning_tokens') or 0), 0)
                for row in prediction_rows
            ),
            'total_tokens': sum(int(row.get('total_tokens') or 0) for row in prediction_rows),
        },
        'cost': total_cost if prediction_rows else None,
        'cost_per_successful_task': total_cost / passed if passed and total_cost else None,
        'details': [
            {
                'id': item.id,
                'scorer': result.scorer,
                'passed': result.passed,
                'reason': result.reason,
                'expected_behavior': item.expected_behavior,
            }
            for item, result in zip(items, scored, strict=True)
        ],
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps(report['scores'], indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
