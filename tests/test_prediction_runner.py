import json
from pathlib import Path

from qwen_mtp_probe.prediction_runner import (
    PredictionRow,
    _openrouter_output,
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


def _eval_row_count(path: Path = Path('data/eval/hermes_v0_eval.jsonl')) -> int:
    return sum(1 for line in path.read_text().splitlines() if line.strip())


def test_stub_prediction_runner_emits_one_prediction_per_eval_item(tmp_path):
    predictions = run_predictions(
        eval_path=Path('data/eval/hermes_v0_eval.jsonl'),
        model='stub-ultra-compact',
        provider='stub',
    )

    assert len(predictions) == _eval_row_count()
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
    assert len(rows) == _eval_row_count()
    assert sum(1 for row in rows if row['output'].startswith('ACTION ')) >= len(rows) // 2


def test_openrouter_output_extracts_content_and_usage_tokens():
    output, tokens, prompt_tokens, total_tokens, cost = _openrouter_output(
        {
            'choices': [{'message': {'content': 'ACTION terminal {"command":"date"}'}}],
            'usage': {'completion_tokens': 5, 'prompt_tokens': 7, 'total_tokens': 12, 'cost': 0.001},
        }
    )

    assert output == 'ACTION terminal {"command":"date"}'
    assert tokens == 5
    assert prompt_tokens == 7
    assert total_tokens == 12
    assert cost == 0.001
