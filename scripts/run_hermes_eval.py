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
    if args.predictions:
        for line in Path(args.predictions).read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            predictions[str(row['id'])] = str(row.get('output', ''))

    scored = []
    for item in items:
        output = predictions.get(item.id, '')
        result = score_output(item.scorer, output)
        scored.append(result)

    report = {
        'run_name': 'baseline-template' if not args.predictions else Path(args.predictions).stem,
        'model': None,
        'eval_path': args.eval,
        'prediction_path': args.predictions,
        'items': len(items),
        'scores': summarize_scores(scored),
        'latency': {},
        'tokens': {},
        'cost_per_successful_task': None,
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
