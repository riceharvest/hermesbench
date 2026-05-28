import json
from pathlib import Path

HARDENING_PATH = Path('data/examples/hermes_compact_traces.lightning_failure_hardening.v0.jsonl')


def _rows() -> list[dict]:
    if not HARDENING_PATH.exists():
        return []
    return [json.loads(line) for line in HARDENING_PATH.read_text().splitlines() if line.strip()]


def _assistant(row: dict) -> str:
    return row['messages'][-1]['content']


def _user(row: dict) -> str:
    return next(message['content'] for message in reversed(row['messages']) if message['role'] == 'user')


def test_lightning_failed_verification_prompts_have_evidence_action_targets():
    rows = _rows()
    assert len(rows) >= 32

    joined_users = '\n'.join(_user(row).lower() for row in rows)
    joined_assistants = '\n'.join(_assistant(row) for row in rows)

    required_prompt_cues = [
        'focused holdout',
        'train/eval split',
        'prediction runner',
        'repository clean',
        'scorer distribution',
        'training prompts reused in eval',
        'unknown scorer',
    ]
    for cue in required_prompt_cues:
        assert cue in joined_users

    required_evidence = [
        'tests/test_eval_holdout.py',
        'scripts/run_hermes_predictions.py',
        'scripts/run_hermes_eval.py',
        'git status --short',
        'collections.Counter',
    ]
    for evidence in required_evidence:
        assert evidence in joined_assistants

    verification_rows = [row for row in rows if 'verification' in row.get('tags', [])]
    assert verification_rows
    assert all(not _assistant(row).startswith('FINAL:') for row in verification_rows)


def test_lightning_scorer_distribution_targets_are_parseable_execute_code_actions():
    rows = [
        row
        for row in _rows()
        if 'scorer_distribution' in row.get('tags', [])
        and 'malformed_action_regression' in row.get('tags', [])
    ]
    assert len(rows) >= 4

    for row in rows:
        assistant = _assistant(row)
        assert assistant.startswith('ACTION execute_code ')
        payload = assistant.removeprefix('ACTION execute_code ')
        args = json.loads(payload)
        assert set(args) == {'code'}
        assert 'collections.Counter' in args['code']
        assert 'data/eval/hermes_v0_eval.jsonl' in args['code']
