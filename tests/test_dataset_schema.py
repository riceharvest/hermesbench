import json
from pathlib import Path


def _jsonl(path: Path):
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_seed_sft_jsonl_has_messages():
    path = Path('data/examples/hermes_compact_traces.seed.jsonl')
    assert path.exists()
    rows = _jsonl(path)
    assert rows
    for row in rows:
        assert 'messages' in row
        assert isinstance(row['messages'], list)
        assert row['messages'][-1]['role'] == 'assistant'
        content = row['messages'][-1]['content']
        assert 'SCRATCH<=80:' in content or 'FINAL:' in content or 'ACTION' in content


def test_seed_eval_jsonl_has_expected_behavior():
    path = Path('data/eval/hermes_v0_eval.seed.jsonl')
    assert path.exists()
    rows = _jsonl(path)
    assert rows
    for row in rows:
        assert {'id', 'input', 'expected_behavior', 'scorer'} <= set(row)
