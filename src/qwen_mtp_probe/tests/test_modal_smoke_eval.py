from __future__ import annotations

from qwen_mtp_probe.modal_smoke_eval import evaluate_smoke_generations, select_smoke_eval_items


def test_select_smoke_eval_items_balances_by_scorer_not_file_order() -> None:
    rows = [
        {'id': 'tool-1', 'input': 'Need current time', 'scorer': 'tool_use_required'},
        {'id': 'tool-2', 'input': 'Need disk', 'scorer': 'tool_use_required'},
        {'id': 'tool-3', 'input': 'Need RAM', 'scorer': 'tool_use_required'},
        {'id': 'final-1', 'input': 'Summarize this', 'scorer': 'concise_final_required'},
        {'id': 'final-2', 'input': 'Answer briefly', 'scorer': 'concise_final_required'},
        {'id': 'repo-1', 'input': 'Inspect repo', 'scorer': 'repo_inspection_required'},
    ]

    selected = select_smoke_eval_items(rows, limit=3)

    assert [item['id'] for item in selected] == ['tool-1', 'final-1', 'repo-1']
    assert [item['scorer'] for item in selected] == [
        'tool_use_required',
        'concise_final_required',
        'repo_inspection_required',
    ]


def test_select_smoke_eval_items_skips_malformed_rows() -> None:
    rows = [
        {'id': 'missing-input', 'scorer': 'tool_use_required'},
        {'id': 'missing-scorer', 'input': 'Need current time'},
        {'id': 'good', 'input': 'Need current time', 'scorer': 'tool_use_required'},
    ]

    assert select_smoke_eval_items(rows, limit=5) == [rows[-1]]


def test_select_smoke_eval_items_reports_scorer_mix() -> None:
    rows = [
        {'id': 'tool-1', 'input': 'Need current time', 'scorer': 'tool_use_required'},
        {'id': 'tool-2', 'input': 'Need disk', 'scorer': 'tool_use_required'},
        {'id': 'final-1', 'input': 'Summarize this', 'scorer': 'concise_final_required'},
    ]

    selected = select_smoke_eval_items(rows, limit=3)

    assert selected.scorer_counts == {'tool_use_required': 2, 'concise_final_required': 1}


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
