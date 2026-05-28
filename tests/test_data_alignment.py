import json
import re
from pathlib import Path

import pytest

from qwen_mtp_probe.ultra_compact import (
    GPT55_STYLE_NAME,
    STYLE_NAME,
    validate_training_assistant,
    validate_ultra_compact_assistant,
)

TRACE_SOURCE_PATHS = sorted(Path('data/examples').glob('hermes_compact_traces*.jsonl')) + sorted(
    Path('data/examples').glob('hermes_hf_*.jsonl')
)
GPT55_TEACHER_PATH = Path('data/examples/hermes_gpt55_teacher_sft.v0.jsonl')
PREFERENCE_PATHS = sorted(Path('data/examples').glob('hermes_preference_pairs*.jsonl'))
PROCESSED_TRAIN_PATH = Path('data/processed/hermes_v0_train.jsonl')
ACTIVE_TRAIN_STYLES = {STYLE_NAME}

VALID_ACTION_TOOLS = {
    'browser_click',
    'browser_console',
    'browser_navigate',
    'browser_type',
    'browser_vision',
    'cronjob',
    'delegate_task',
    'execute_code',
    'memory',
    'patch',
    'process',
    'read_file',
    'search_files',
    'skill_manage',
    'skill_view',
    'skills_list',
    'terminal',
    'todo',
    'vision_analyze',
    'web_extract',
    'web_search',
    'write_file',
    'x_search',
}

OBSOLETE_SCRATCH_MARKERS = ('SCRATCH<=64', 'SCRATCH<=80', 'SCRATCH<=96')
FORBIDDEN_REASONING_TARGET_PATTERNS = [
    re.compile(r"here(?:'|’)s a thinking process", re.I),
    re.compile(r'thinking process', re.I),
    re.compile(r'Analyze User Input', re.I),
    re.compile(r'\b\d+\.\s+\*\*Analyze\b', re.I),
    re.compile(r'</?think\b', re.I),
]
HIGH_RISK_SECRET_PATTERNS = [
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r"(?:postgres|mysql|mongodb)://[^\s\"']+:[^\s\"']+@", re.I),
    re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----'),
]
UNSAFE_ACTION_TARGET_PATTERNS = [
    re.compile(r'\brm\s+-[A-Za-z]*r[A-Za-z]*f\b'),
    re.compile(r'\bfind\b[^\n;|&]*\s-delete\b'),
    re.compile(r'\bchmod\b'),
    re.compile(r'\bchown\b'),
    re.compile(r'\bmkfs(?:\.[A-Za-z0-9_+-]+)?\b'),
]


def _jsonl(path: Path):
    for line_number, line in enumerate(path.read_text().splitlines(), 1):
        if line.strip():
            yield line_number, json.loads(line)


def _action_payload(content: str):
    match = re.search(
        r'(?:^|\n)ACTION\s+([A-Za-z_][A-Za-z0-9_]*)\s+(\{.*\})\s*$',
        content.strip(),
        re.S,
    )
    if not match:
        return None
    return match.group(1), match.group(2)


def _assert_action_is_parseable(path: Path, line_number: int, content: str) -> None:
    if 'ACTION ' not in content:
        return
    payload = _action_payload(content)
    assert payload is not None, f'{path}:{line_number}: ACTION must be `ACTION tool {{json}}`'
    tool, raw_args = payload
    assert tool in VALID_ACTION_TOOLS, f'{path}:{line_number}: unsupported action tool {tool}'
    try:
        args = json.loads(raw_args)
    except json.JSONDecodeError as exc:  # pragma: no cover - assertion path
        pytest.fail(f'{path}:{line_number}: invalid ACTION JSON for {tool}: {exc}')
    assert isinstance(args, dict), f'{path}:{line_number}: ACTION args must be a JSON object'


def test_all_sft_trace_sources_are_ultra_compact_and_parseable():
    assert TRACE_SOURCE_PATHS
    for path in TRACE_SOURCE_PATHS:
        for line_number, row in _jsonl(path):
            content = row['messages'][-1]['content']
            validate_ultra_compact_assistant(content)
            assert not any(marker in content for marker in OBSOLETE_SCRATCH_MARKERS)
            _assert_action_is_parseable(path, line_number, content)


def test_gpt55_teacher_traces_are_compact_enough_and_parseable():
    rows = list(_jsonl(GPT55_TEACHER_PATH))
    assert len(rows) == 4182
    for line_number, row in rows:
        assert row['style'] == GPT55_STYLE_NAME
        content = row['messages'][-1]['content']
        validate_training_assistant(content, GPT55_STYLE_NAME)
        _assert_action_is_parseable(GPT55_TEACHER_PATH, line_number, content)


def test_processed_train_matches_compact_contract():
    rows = list(_jsonl(PROCESSED_TRAIN_PATH))
    assert len(rows) == 6579
    assert {row['style'] for _, row in rows} == ACTIVE_TRAIN_STYLES
    for line_number, row in rows:
        for message in row['messages']:
            if message.get('role') != 'assistant':
                continue
            content = message['content']
            validate_training_assistant(content, row['style'])
            assert not any(marker in content for marker in OBSOLETE_SCRATCH_MARKERS)
            for pattern in FORBIDDEN_REASONING_TARGET_PATTERNS:
                assert not pattern.search(content), f'{PROCESSED_TRAIN_PATH}:{line_number}: {pattern.pattern}'
            _assert_action_is_parseable(PROCESSED_TRAIN_PATH, line_number, content)


def test_live_tool_prompts_have_action_targets_in_processed_train():
    rows = list(_jsonl(PROCESSED_TRAIN_PATH))
    matches = []
    for line_number, row in rows:
        user_text = ' '.join(
            message.get('content', '') for message in row['messages'] if message.get('role') == 'user'
        )
        if 'what time is it' in user_text.lower():
            content = row['messages'][-1]['content']
            matches.append((line_number, content))
            assert content.startswith('ACTION terminal '), f'{PROCESSED_TRAIN_PATH}:{line_number}'
            assert 'date' in content, f'{PROCESSED_TRAIN_PATH}:{line_number}'
    assert matches, 'expected at least one What time is it? regression row'


def test_verification_prompts_require_evidence_actions_in_processed_train():
    rows = list(_jsonl(PROCESSED_TRAIN_PATH))
    verification_markers = (
        'verify',
        'verified',
        'check whether',
        'did the',
        'does the report',
        'after the run',
        'tests pass',
    )
    matches = []
    for line_number, row in rows:
        user_text = ' '.join(
            message.get('content', '') for message in row['messages'] if message.get('role') == 'user'
        ).lower()
        if not any(marker in user_text for marker in verification_markers):
            continue
        content = row['messages'][-1]['content']
        if any(marker in content for marker in ('read_file', 'search_files', 'execute_code', 'terminal')):
            matches.append((line_number, content))
            assert content.startswith('ACTION ') or '\n\nACTION ' in content, f'{PROCESSED_TRAIN_PATH}:{line_number}'
    assert len(matches) >= 540, 'expected a strong verification-action training slice'


def test_regression_prompts_from_failed_smoke_have_specific_evidence_actions():
    rows = list(_jsonl(PROCESSED_TRAIN_PATH))
    prompt_expectations = {
        'train/eval split is clean': ('pytest tests/test_eval_holdout.py', 'run_hermes_eval.py'),
        'prediction runner still work': ('run_hermes_predictions.py', 'hermes-v0-predictions'),
        'scorer distribution without extra background': ('execute_code', 'Counter', 'scorer'),
    }
    found = {key: False for key in prompt_expectations}
    for _, row in rows:
        user_text = ' '.join(
            message.get('content', '') for message in row['messages'] if message.get('role') == 'user'
        ).lower()
        content = row['messages'][-1]['content']
        for prompt_fragment, expected_markers in prompt_expectations.items():
            if prompt_fragment not in user_text:
                continue
            if content.startswith('FINAL:'):
                continue
            if any(marker in content for marker in expected_markers):
                found[prompt_fragment] = True
    assert found == {key: True for key in prompt_expectations}


def test_preference_chosen_outputs_are_valid_compact_targets():
    assert PREFERENCE_PATHS
    for path in PREFERENCE_PATHS:
        for line_number, row in _jsonl(path):
            chosen = row['chosen']
            validate_ultra_compact_assistant(chosen)
            assert not any(marker in chosen for marker in OBSOLETE_SCRATCH_MARKERS)
            _assert_action_is_parseable(path, line_number, chosen)
            assert row['rejected'].strip()


def test_checked_in_data_has_no_obvious_raw_secret_values():
    data_paths = list(Path('data').glob('**/*.jsonl'))
    assert data_paths
    for path in data_paths:
        text = path.read_text()
        for pattern in HIGH_RISK_SECRET_PATTERNS:
            assert not pattern.search(text), f'{path}: matched high-risk secret pattern {pattern.pattern}'


def test_processed_train_has_no_destructive_action_targets():
    for line_number, row in _jsonl(PROCESSED_TRAIN_PATH):
        for message in row['messages']:
            if message.get('role') != 'assistant':
                continue
            content = message['content']
            for pattern in UNSAFE_ACTION_TARGET_PATTERNS:
                assert not pattern.search(content), f'{PROCESSED_TRAIN_PATH}:{line_number}: {pattern.pattern}'
