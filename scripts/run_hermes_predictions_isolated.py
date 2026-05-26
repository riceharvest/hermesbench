from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from dataclasses import asdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))

from qwen_mtp_probe.datasets import EvalItem, load_eval_jsonl
from qwen_mtp_probe.prediction_runner import PredictionRow, _predict_openrouter


def _worker(item_dict: dict, args: dict, queue: mp.Queue) -> None:
    item = EvalItem(**item_dict)
    try:
        row = _predict_openrouter(
            item,
            model=args['model'],
            provider=args['provider'],
            max_tokens=args['max_tokens'],
            reasoning_effort=args['reasoning_effort'],
            reasoning_exclude=args['reasoning_exclude'],
            retry_token_budgets=args['retry_token_budgets'],
        )
        queue.put((item.id, asdict(row), None))
    except Exception as exc:  # noqa: BLE001 - persisted as eval artifact, not hidden
        row = PredictionRow(
            id=item.id,
            input=item.input,
            output='OPENROUTER_ERROR',
            model=args['model'],
            latency_ms=0.0,
            output_tokens=1,
            provider=args['provider'],
        )
        queue.put((item.id, asdict(row), repr(exc)))


def _timeout_row(item: EvalItem, model: str, provider: str, elapsed_ms: float) -> dict:
    return asdict(
        PredictionRow(
            id=item.id,
            input=item.input,
            output='OPENROUTER_TIMEOUT',
            model=model,
            latency_ms=elapsed_ms,
            output_tokens=1,
            provider=provider,
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description='Run OpenRouter predictions with per-item process timeouts.')
    parser.add_argument('--eval', required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('--model', required=True)
    parser.add_argument('--provider', default='openrouter', choices=['openrouter'])
    parser.add_argument('--reasoning-effort', default='high')
    parser.add_argument('--max-tokens', type=int, default=1024)
    parser.add_argument('--workers', type=int, default=4)
    parser.add_argument('--item-timeout', type=float, default=120.0)
    parser.add_argument('--include-reasoning', action='store_true')
    parser.add_argument('--retry-token-budgets', action='store_true')
    args = parser.parse_args()

    items = load_eval_jsonl(Path(args.eval))
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)

    worker_args = {
        'model': args.model,
        'provider': args.provider,
        'max_tokens': args.max_tokens,
        'reasoning_effort': args.reasoning_effort,
        'reasoning_exclude': not args.include_reasoning,
        'retry_token_budgets': args.retry_token_budgets,
    }

    queue: mp.Queue = mp.Queue()
    next_index = 0
    running: dict[str, tuple[mp.Process, EvalItem, float]] = {}
    written = 0
    errors = 0
    timeouts = 0

    with output.open('w', encoding='utf-8') as handle:
        while next_index < len(items) or running:
            while next_index < len(items) and len(running) < args.workers:
                item = items[next_index]
                process = mp.Process(target=_worker, args=(item.__dict__, worker_args, queue))
                process.start()
                running[item.id] = (process, item, time.perf_counter())
                next_index += 1

            while not queue.empty():
                item_id, row, error = queue.get()
                proc, _item, _started = running.pop(item_id, (None, None, None))
                if proc is not None:
                    proc.join(timeout=0.1)
                if error:
                    row['error'] = error
                    errors += 1
                handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
                handle.flush()
                written += 1
                print(json.dumps({'written': written, 'id': item_id, 'error': bool(error)}, sort_keys=True), flush=True)

            now = time.perf_counter()
            for item_id, (proc, item, started) in list(running.items()):
                if not proc.is_alive():
                    proc.join(timeout=0.1)
                    if item_id in running:
                        running.pop(item_id, None)
                        row = _timeout_row(item, args.model, args.provider, (now - started) * 1000)
                        row['error'] = 'process exited without result'
                        handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
                        handle.flush()
                        written += 1
                        errors += 1
                        print(json.dumps({'written': written, 'id': item_id, 'error': True}, sort_keys=True), flush=True)
                elif now - started > args.item_timeout:
                    proc.terminate()
                    proc.join(timeout=2)
                    if proc.is_alive():
                        proc.kill()
                        proc.join(timeout=2)
                    running.pop(item_id, None)
                    row = _timeout_row(item, args.model, args.provider, (now - started) * 1000)
                    handle.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n')
                    handle.flush()
                    written += 1
                    timeouts += 1
                    print(json.dumps({'written': written, 'id': item_id, 'timeout': True}, sort_keys=True), flush=True)

            time.sleep(0.2)

    print(json.dumps({'output': str(output), 'predictions': written, 'errors': errors, 'timeouts': timeouts}, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
