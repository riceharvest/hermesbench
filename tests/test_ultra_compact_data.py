import json

import pytest

from qwen_mtp_probe.datasets import load_chat_jsonl
from qwen_mtp_probe.ultra_compact import (
    UltraCompactViolation,
    build_ultra_compact_examples,
    summarize_ultra_compact_dataset,
    validate_quality_gates,
    validate_ultra_compact_assistant,
    write_jsonl,
)


def test_validate_accepts_action_only_trace():
    validate_ultra_compact_assistant('ACTION terminal {"command":"date"}')


def test_validate_accepts_scratch_32_then_action():
    validate_ultra_compact_assistant(
        'SCRATCH<=32:\nNeed live fact.\n\nACTION terminal {"command":"date"}'
    )


def test_validate_rejects_old_scratch_80_style():
    with pytest.raises(UltraCompactViolation, match='SCRATCH<=32'):
        validate_ultra_compact_assistant(
            'SCRATCH<=80:\nNeed inspect workspace, not create new repo. Find qwen folders.\n\n'
            'ACTION search_files {"pattern":"*qwen*"}'
        )


def test_build_ultra_compact_examples_compresses_seed_traces():
    rows = build_ultra_compact_examples(['data/examples/hermes_compact_traces.seed.jsonl'])

    assert len(rows) >= 6
    assert all(row['style'] == 'hermes-ultra-compact-v0' for row in rows)
    assert all('SCRATCH<=80' not in row['messages'][-1]['content'] for row in rows)
    assert any(row['messages'][-1]['content'].startswith('ACTION ') for row in rows)
    assert any(row['messages'][-1]['content'].startswith('SCRATCH<=32:') for row in rows)


def test_write_jsonl_outputs_loadable_training_file(tmp_path):
    rows = build_ultra_compact_examples(['data/examples/hermes_compact_traces.seed.jsonl'])
    output = tmp_path / 'processed' / 'hermes_v0_train.jsonl'

    write_jsonl(output, rows)

    loaded = load_chat_jsonl(output)
    assert len(loaded) == len(rows)
    first = json.loads(output.read_text().splitlines()[0])
    assert first['source_style'] == 'compact-seed'
    assert first['style'] == 'hermes-ultra-compact-v0'


def test_dataset_summary_counts_output_kinds_and_tools():
    rows = build_ultra_compact_examples(
        [
            'data/examples/hermes_compact_traces.seed.jsonl',
            'data/examples/hermes_compact_traces.v0.jsonl',
        ]
    )

    summary = summarize_ultra_compact_dataset(rows)

    assert summary['total'] >= 30
    assert summary['by_output_kind']['action_only'] >= 10
    assert summary['by_output_kind']['scratch_action'] >= 10
    assert summary['by_output_kind']['final_only'] >= 5
    assert summary['by_tool']['terminal'] >= 3
    assert summary['by_tool']['search_files'] >= 3
    assert summary['by_tool']['read_file'] >= 3
    assert summary['max_scratch_words'] <= 32
    assert summary['invalid_examples'] == []


def test_quality_gates_reject_tiny_or_unbalanced_datasets():
    rows = build_ultra_compact_examples(['data/examples/hermes_compact_traces.seed.jsonl'])

    with pytest.raises(UltraCompactViolation, match='at least 30 examples'):
        validate_quality_gates(rows, min_examples=30)
