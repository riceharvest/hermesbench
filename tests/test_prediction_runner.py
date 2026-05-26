import json
from pathlib import Path

from qwen_mtp_probe.prediction_runner import (
    PredictionRow,
    run_predictions,
    validate_prediction_row,
    write_predictions_jsonl,
)


def test_validate_prediction_row_requires_eval_id_output_and_metrics():
    row = PredictionRow(
        id='tool_choice_live_time_002',
        input='what time is it?',
        output='ACTION terminal {"command":"date"}',
        model='stub-ultra-compact',
        latency_ms=1.2,
        output_tokens=3,
        provider='stub',
    )

    validate_prediction_row(row)


def test_stub_prediction_runner_emits_one_prediction_per_eval_item(tmp_path):
    predictions = run_predictions(
        eval_path=Path('data/eval/hermes_v0_eval.jsonl'),
        model='stub-ultra-compact',
        provider='stub',
    )

    assert len(predictions) == 20
    assert all(pred.id for pred in predictions)
    assert all(pred.model == 'stub-ultra-compact' for pred in predictions)
    assert any(pred.output.startswith('ACTION ') for pred in predictions)
    assert any(pred.output.startswith('SCRATCH<=32:') for pred in predictions)
    assert any(pred.output.startswith('FINAL:') for pred in predictions)
    assert all(pred.latency_ms >= 0 for pred in predictions)
    assert all(pred.output_tokens > 0 for pred in predictions)

    output_path = tmp_path / 'predictions.jsonl'
    write_predictions_jsonl(output_path, predictions)
    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert rows[0].keys() >= {'id', 'input', 'output', 'model', 'provider', 'latency_ms', 'output_tokens'}


def test_stub_predictions_score_above_empty_baseline(tmp_path):
    predictions = run_predictions(
        eval_path=Path('data/eval/hermes_v0_eval.jsonl'),
        model='stub-ultra-compact',
        provider='stub',
    )
    output_path = tmp_path / 'predictions.jsonl'
    write_predictions_jsonl(output_path, predictions)

    # Keep this test local to the library layer: the CLI eval runner reads this same schema.
    rows = [json.loads(line) for line in output_path.read_text().splitlines()]
    assert len(rows) == 20
    assert sum(1 for row in rows if row['output'].startswith('ACTION ')) >= 8
