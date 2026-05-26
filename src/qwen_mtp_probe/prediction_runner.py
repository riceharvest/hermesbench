from __future__ import annotations

import argparse
import json
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable

from qwen_mtp_probe.datasets import EvalItem, load_eval_jsonl
from qwen_mtp_probe.ultra_compact import validate_ultra_compact_assistant


@dataclass(frozen=True)
class PredictionRow:
    id: str
    input: str
    output: str
    model: str
    latency_ms: float
    output_tokens: int
    provider: str


def _token_count(text: str) -> int:
    return len(text.split())


def validate_prediction_row(row: PredictionRow) -> None:
    if not row.id.strip():
        raise ValueError('prediction id must be non-empty')
    if not row.input.strip():
        raise ValueError('prediction input must be non-empty')
    if not row.output.strip():
        raise ValueError('prediction output must be non-empty')
    if not row.model.strip():
        raise ValueError('prediction model must be non-empty')
    if not row.provider.strip():
        raise ValueError('prediction provider must be non-empty')
    if row.latency_ms < 0:
        raise ValueError('prediction latency_ms must be non-negative')
    if row.output_tokens <= 0:
        raise ValueError('prediction output_tokens must be positive')


def _stub_output(item: EvalItem) -> str:
    text = item.input.lower()
    scorer = item.scorer

    if scorer == 'tool_use_required':
        if 'hash' in text or 'sha256' in text:
            return 'ACTION terminal {"command":"printf %s \'hermes-agent-v0\' | sha256sum"}'
        if 'calculate' in text or any(ch.isdigit() for ch in text):
            return 'ACTION execute_code {"code":"print(3847 * 219)"}'
        if 'time' in text:
            return 'ACTION terminal {"command":"TZ=Europe/Amsterdam date"}'
        return 'ACTION terminal {"command":"uname -a && cat /etc/os-release"}'

    if scorer == 'repo_inspection_required':
        if 'commit' in text or 'changed' in text:
            return 'ACTION terminal {"command":"git log --oneline -5 && git status --short"}'
        return 'ACTION search_files {"path":"/home/dario/Documents/dev workspace","pattern":"*qwen*","target":"files"}'

    if scorer == 'verification_required':
        if 'training' in text:
            return 'SCRATCH<=32:\nNeed verify data and dry-run first.\n\nACTION terminal {"command":"test -s data/processed/hermes_v0_train.jsonl && PYTHONPATH=src uv run python -m qwen_mtp_probe.train_sft --config configs/qwen36-hermes-v0-sft.yaml --dry-run"}'
        return 'SCRATCH<=32:\nNeed fresh evidence before claiming success.\n\nACTION read_file {"path":"reports/modal-sglang-single-h100-bench.json"}'

    if scorer == 'ultra_compact_style':
        if 'summarize' in text or 'status' in text:
            return 'FINAL:\nCurrent stage: v0-sft-main prep. MTP probe is done; train normal decode first, then refresh MTP.'
        if 'diagnose' in text or 'server' in text:
            return 'SCRATCH<=32:\nNeed startup log before changing flags.\n\nACTION read_file {"path":"reports/modal-sglang-bench.json"}'
        return 'ACTION read_file {"path":"reports/modal-sglang-single-h100-bench.json"}'

    if scorer == 'no_unnecessary_clarification':
        if 'test' in text:
            return 'ACTION terminal {"command":"uv run --extra test python -m pytest -q","timeout":180}'
        return 'ACTION search_files {"path":"/home/dario/Documents/dev workspace","pattern":"*qwen*","target":"files"}'

    if scorer == 'concise_final_required':
        return 'FINAL:\nNext: run held-out eval predictions, mine more ultra-compact traces, then launch v0-sft-main only after baseline exists.'

    return 'FINAL:\nNo stub output available.'


def _predict_stub(item: EvalItem, model: str, provider: str) -> PredictionRow:
    start = time.perf_counter()
    output = _stub_output(item)
    # Stub provider should still obey the target output contract.
    validate_ultra_compact_assistant(output)
    latency_ms = (time.perf_counter() - start) * 1000
    return PredictionRow(
        id=item.id,
        input=item.input,
        output=output,
        model=model,
        latency_ms=latency_ms,
        output_tokens=_token_count(output),
        provider=provider,
    )


def run_predictions(eval_path: Path, model: str, provider: str = 'stub') -> list[PredictionRow]:
    items = load_eval_jsonl(eval_path)
    if provider != 'stub':
        raise NotImplementedError(f'provider {provider!r} is not implemented yet')
    predictions = [_predict_stub(item, model=model, provider=provider) for item in items]
    for prediction in predictions:
        validate_prediction_row(prediction)
    return predictions


def write_predictions_jsonl(path: str | Path, predictions: Iterable[PredictionRow]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        ''.join(json.dumps(asdict(prediction), ensure_ascii=False, sort_keys=True) + '\n' for prediction in predictions)
    )


def main() -> None:
    parser = argparse.ArgumentParser(description='Run Hermes eval prompts through a prediction provider.')
    parser.add_argument('--eval', required=True, help='Eval JSONL path')
    parser.add_argument('--output', required=True, help='Prediction JSONL output path')
    parser.add_argument('--model', default='stub-ultra-compact', help='Model label to record')
    parser.add_argument('--provider', default='stub', choices=['stub'], help='Prediction provider')
    args = parser.parse_args()

    predictions = run_predictions(eval_path=Path(args.eval), model=args.model, provider=args.provider)
    write_predictions_jsonl(args.output, predictions)
    print(json.dumps({'output': args.output, 'predictions': len(predictions), 'model': args.model, 'provider': args.provider}, indent=2))


if __name__ == '__main__':
    main()
