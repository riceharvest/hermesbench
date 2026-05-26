import json
from pathlib import Path


EVAL_PATH = Path('data/eval/hermes_v0_eval.jsonl')
TRAIN_PATH = Path('data/processed/hermes_v0_train.jsonl')
EXPECTED_EVAL_FIELDS = {'id', 'input', 'expected_behavior', 'scorer', 'tags'}
VALID_SCORERS = {
    'tool_use_required',
    'repo_inspection_required',
    'verification_required',
    'concise_final_required',
    'no_unnecessary_clarification',
    'ultra_compact_style',
}


def _train_user_inputs(path: Path) -> set[str]:
    inputs = set()
    for line in path.read_text().splitlines():
        row = json.loads(line)
        users = [m['content'] for m in row['messages'] if m['role'] == 'user']
        inputs.add(users[-1].strip().lower())
    return inputs


def _eval_rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _eval_inputs(path: Path) -> set[str]:
    return {row['input'].strip().lower() for row in _eval_rows(path)}


def test_eval_inputs_are_held_out_from_processed_train_data():
    train_inputs = _train_user_inputs(TRAIN_PATH)
    eval_inputs = _eval_inputs(EVAL_PATH)

    assert train_inputs.isdisjoint(eval_inputs)


def test_eval_has_expected_size_schema_and_scorers():
    rows = _eval_rows(EVAL_PATH)

    assert len(rows) == 300
    assert {row['scorer'] for row in rows} <= VALID_SCORERS
    assert len({row['id'] for row in rows}) == len(rows)
    assert len({row['input'].strip().lower() for row in rows}) == len(rows)

    for row in rows:
        assert set(row) == EXPECTED_EVAL_FIELDS
        assert row['id']
        assert row['input']
        assert row['expected_behavior']
        assert isinstance(row['tags'], list) and row['tags']
