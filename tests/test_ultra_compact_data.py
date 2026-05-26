import json

import pytest

from qwen_mtp_probe.datasets import load_chat_jsonl
from qwen_mtp_probe.ultra_compact import (
    UltraCompactViolation,
    build_ultra_compact_examples,
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
