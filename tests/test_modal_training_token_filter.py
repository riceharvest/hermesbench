from __future__ import annotations

from qwen_mtp_probe.modal_training_token_filter import filter_tokenized_examples_by_length


def test_filter_tokenized_examples_by_length_drops_over_budget_rows() -> None:
    rows = [
        {'id': 'short', 'input_ids': [1, 2, 3], 'labels': [-100, 2, 3]},
        {'id': 'long', 'input_ids': list(range(6)), 'labels': [-100, -100, 2, 3, 4, 5]},
        {'id': 'edge', 'input_ids': list(range(5)), 'labels': [-100, 1, 2, 3, 4]},
    ]

    kept, stats = filter_tokenized_examples_by_length(rows, max_tokens=5)

    assert [row['id'] for row in kept] == ['short', 'edge']
    assert stats == {'before': 3, 'after': 2, 'dropped_over_token_budget': 1, 'max_train_tokens': 5}


def test_filter_tokenized_examples_by_length_is_noop_without_budget() -> None:
    rows = [{'id': 'long', 'input_ids': list(range(6)), 'labels': list(range(6))}]

    kept, stats = filter_tokenized_examples_by_length(rows, max_tokens=None)

    assert kept == rows
    assert stats == {'before': 1, 'after': 1, 'dropped_over_token_budget': 0, 'max_train_tokens': None}
