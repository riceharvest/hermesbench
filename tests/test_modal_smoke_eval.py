from __future__ import annotations

from qwen_mtp_probe.modal_smoke_eval import evaluate_smoke_generations, select_smoke_eval_items


def test_select_smoke_eval_items_keeps_order_and_limit() -> None:
    rows = [
        {'id': 'a', 'input': 'Need current time', 'scorer': 'tool_use_required'},
        {'id': 'b', 'input': 'Summarize this', 'scorer': 'concise_final_required'},
        {'id': 'c', 'input': 'Inspect repo', 'scorer': 'repo_inspection_required'},
    ]

    selected = select_smoke_eval_items(rows, limit=2)

    assert [item['id'] for item in selected] == ['a', 'b']
    assert selected[0]['input'] == 'Need current time'
    assert selected[0]['scorer'] == 'tool_use_required'


def test_select_smoke_eval_items_skips_malformed_rows() -> None:
    rows = [
        {'id': 'missing-input', 'scorer': 'tool_use_required'},
        {'id': 'missing-scorer', 'input': 'Need current time'},
        {'id': 'good', 'input': 'Need current time', 'scorer': 'tool_use_required'},
    ]

    assert select_smoke_eval_items(rows, limit=5) == [rows[-1]]


def test_evaluate_smoke_generations_requires_task_score_and_ultra_compact_style() -> None:
    items = [
        {'id': 'time', 'input': 'Give me the current UTC date and time.', 'scorer': 'tool_use_required'},
        {'id': 'bad', 'input': 'Give me the current UTC date and time.', 'scorer': 'tool_use_required'},
    ]
    generations = {
        'time': 'ACTION terminal {"command":"date -u"}',
        'bad': 'Here is a thinking process:\n1. I should answer from memory.',
    }

    report = evaluate_smoke_generations(items, generations)

    assert report['total'] == 2
    assert report['passed'] == 1
    assert report['failed'] == 1
    assert report['pass_rate'] == 0.5
    assert report['items'][0]['passed'] is True
    assert report['items'][0]['task_passed'] is True
    assert report['items'][0]['style_passed'] is True
    assert report['items'][1]['passed'] is False
    assert report['items'][1]['task_passed'] is False
    assert report['items'][1]['style_passed'] is False
