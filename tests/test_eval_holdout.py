import json
from pathlib import Path


def _train_user_inputs(path: Path) -> set[str]:
    inputs = set()
    for line in path.read_text().splitlines():
        row = json.loads(line)
        users = [m['content'] for m in row['messages'] if m['role'] == 'user']
        inputs.add(users[-1].strip().lower())
    return inputs


def _eval_inputs(path: Path) -> set[str]:
    return {
        json.loads(line)['input'].strip().lower()
        for line in path.read_text().splitlines()
        if line.strip()
    }


def test_eval_inputs_are_held_out_from_processed_train_data():
    train_inputs = _train_user_inputs(Path('data/processed/hermes_v0_train.jsonl'))
    eval_inputs = _eval_inputs(Path('data/eval/hermes_v0_eval.jsonl'))

    assert train_inputs.isdisjoint(eval_inputs)
