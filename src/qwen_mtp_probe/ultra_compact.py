from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Iterable

from qwen_mtp_probe.datasets import load_chat_jsonl

STYLE_NAME = 'hermes-ultra-compact-v0'
SOURCE_STYLE = 'compact-seed'
MAX_SCRATCH_WORDS = 32


class UltraCompactViolation(ValueError):
    pass


def _assistant_payload(row: dict[str, Any]) -> str:
    messages = row.get('messages')
    if not isinstance(messages, list) or not messages:
        raise UltraCompactViolation('row must contain non-empty messages')
    last = messages[-1]
    if not isinstance(last, dict) or last.get('role') != 'assistant':
        raise UltraCompactViolation('last message must be assistant')
    content = last.get('content')
    if not isinstance(content, str) or not content.strip():
        raise UltraCompactViolation('assistant content must be non-empty')
    return content.strip()


def _word_count(text: str) -> int:
    return len(re.findall(r"\S+", text))


def validate_ultra_compact_assistant(content: str) -> None:
    stripped = content.strip()
    if not stripped:
        raise UltraCompactViolation('assistant content must be non-empty')
    if 'SCRATCH<=80' in stripped or 'SCRATCH<=64' in stripped:
        raise UltraCompactViolation('use SCRATCH<=32, ACTION-only, or FINAL-only')

    if stripped.startswith('ACTION '):
        return
    if stripped.startswith('FINAL:'):
        return
    if stripped.startswith('SCRATCH<=32:\n'):
        try:
            scratch, rest = stripped.removeprefix('SCRATCH<=32:\n').split('\n\n', 1)
        except ValueError as exc:
            raise UltraCompactViolation('SCRATCH<=32 must be followed by blank line and ACTION/FINAL') from exc
        if _word_count(scratch) > MAX_SCRATCH_WORDS:
            raise UltraCompactViolation('scratch exceeds 32 words')
        if not (rest.startswith('ACTION ') or rest.startswith('FINAL:')):
            raise UltraCompactViolation('SCRATCH<=32 must lead to ACTION or FINAL')
        return

    raise UltraCompactViolation('assistant must start with ACTION, FINAL:, or SCRATCH<=32')


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = Path(path)
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(p.read_text().splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f'{p}:{line_number}: invalid JSON: {exc.msg}') from exc
        if not isinstance(row, dict):
            raise ValueError(f'{p}:{line_number}: expected JSON object')
        rows.append(row)
    return rows


def _extract_action_or_final(content: str) -> tuple[str | None, str | None]:
    marker_positions = []
    for marker in ('\n\nACTION ', '\nACTION ', 'ACTION '):
        pos = content.find(marker)
        if pos >= 0:
            marker_positions.append((pos, 'ACTION'))
    for marker in ('\n\nFINAL:', '\nFINAL:', 'FINAL:'):
        pos = content.find(marker)
        if pos >= 0:
            marker_positions.append((pos, 'FINAL'))
    if not marker_positions:
        return None, None
    pos, kind = min(marker_positions, key=lambda item: item[0])
    payload = content[pos:].strip()
    if kind == 'ACTION' and not payload.startswith('ACTION '):
        payload = payload[payload.find('ACTION '):]
    if kind == 'FINAL' and not payload.startswith('FINAL:'):
        payload = payload[payload.find('FINAL:'):]
    return kind, payload


def _extract_scratch(content: str) -> str:
    if not content.startswith('SCRATCH<='):
        return ''
    _, _, after_header = content.partition('\n')
    before_action = re.split(r'\n\s*\n(?=ACTION |FINAL:)', after_header, maxsplit=1)[0]
    return ' '.join(before_action.split())


def _compress_scratch(scratch: str) -> str:
    if not scratch:
        return ''
    first_clause = re.split(r'(?<=[.;!?])\s+', scratch, maxsplit=1)[0].strip()
    words = first_clause.split()
    if len(words) > MAX_SCRATCH_WORDS:
        words = words[:MAX_SCRATCH_WORDS]
    return ' '.join(words).rstrip(' ,;')


def _is_obvious_action_only(user_text: str, action_payload: str) -> bool:
    lowered = user_text.lower()
    if 'what os' in lowered or 'what time' in lowered or 'current date' in lowered:
        return True
    if action_payload.startswith('ACTION read_file') and ('did ' in lowered or 'worked' in lowered):
        return True
    return False


def compress_assistant_content(user_text: str, content: str) -> str:
    stripped = content.strip()
    if stripped.startswith('FINAL:'):
        validate_ultra_compact_assistant(stripped)
        return stripped
    if stripped.startswith('ACTION '):
        validate_ultra_compact_assistant(stripped)
        return stripped

    kind, payload = _extract_action_or_final(stripped)
    if payload is None:
        raise UltraCompactViolation('cannot find ACTION or FINAL payload')
    if kind == 'ACTION' and _is_obvious_action_only(user_text, payload):
        result = payload
    else:
        scratch = _compress_scratch(_extract_scratch(stripped))
        if scratch:
            result = f'SCRATCH<=32:\n{scratch}\n\n{payload}'
        else:
            result = payload
    validate_ultra_compact_assistant(result)
    return result


def build_ultra_compact_examples(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        # Validate source schema first so malformed rows fail with precise existing errors.
        load_chat_jsonl(path)
        for row in _read_jsonl(path):
            messages = [dict(message) for message in row['messages']]
            user_text = next(
                (m['content'] for m in reversed(messages[:-1]) if m.get('role') == 'user'),
                '',
            )
            messages[-1]['content'] = compress_assistant_content(user_text, messages[-1]['content'])
            new_row = {
                **{k: v for k, v in row.items() if k != 'messages'},
                'messages': messages,
                'style': STYLE_NAME,
                'source_style': row.get('style', SOURCE_STYLE),
            }
            fingerprint = json.dumps(new_row['messages'], sort_keys=True, ensure_ascii=False)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            _assistant_payload(new_row)
            validate_ultra_compact_assistant(new_row['messages'][-1]['content'])
            output.append(new_row)
    return output


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(''.join(json.dumps(row, ensure_ascii=False, sort_keys=True) + '\n' for row in rows))


def main() -> None:
    parser = argparse.ArgumentParser(description='Build Hermes ultra-compact v0 SFT JSONL.')
    parser.add_argument('--input', action='append', required=True, help='Source chat JSONL path')
    parser.add_argument('--output', required=True, help='Output processed JSONL path')
    args = parser.parse_args()

    rows = build_ultra_compact_examples(args.input)
    write_jsonl(args.output, rows)
    print(json.dumps({'output': args.output, 'examples': len(rows), 'style': STYLE_NAME}, indent=2))


if __name__ == '__main__':
    main()
