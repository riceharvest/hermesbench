import json
import re
from pathlib import Path

import pytest

from qwen_mtp_probe.ultra_compact import validate_ultra_compact_assistant

TRACE_SOURCE_PATHS = sorted(Path('data/examples').glob('hermes_compact_traces*.jsonl'))
PREFERENCE_PATHS = sorted(Path('data/examples').glob('hermes_preference_pairs*.jsonl'))
PROCESSED_TRAIN_PATH = Path('data/processed/hermes_v0_train.jsonl')

VALID_ACTION_TOOLS = {
    'execute_code',
    'patch',
    'read_file',
    'search_files',
    'terminal',
    'web_extract',
    'web_search',
    'write_file',
}

OBSOLETE_SCRATCH_MARKERS = ('SCRATCH<=64', 'SCRATCH<=80', 'SCRATCH<=96')
HIGH_RISK_SECRET_PATTERNS = [
    re.compile(r'sk-[A-Za-z0-9]{20,}'),
    re.compile(r"(?:postgres|mysql|mongodb)://[^\s\"']+:[^\s\"']+@", re.I),
    re.compile(r'-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----'),
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


def test_processed_train_matches_ultra_compact_contract():
    rows = list(_jsonl(PROCESSED_TRAIN_PATH))
    assert len(rows) == 2250
    for line_number, row in rows:
        assert row['style'] == 'hermes-ultra-compact-v0'
        assert row['messages'][-1]['role'] == 'assistant'
        content = row['messages'][-1]['content']
        validate_ultra_compact_assistant(content)
        assert not any(marker in content for marker in OBSOLETE_SCRATCH_MARKERS)
        _assert_action_is_parseable(PROCESSED_TRAIN_PATH, line_number, content)


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
