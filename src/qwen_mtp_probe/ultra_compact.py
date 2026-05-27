from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from qwen_mtp_probe.datasets import load_chat_jsonl

STYLE_NAME = 'hermes-ultra-compact-v0'
GPT55_STYLE_NAME = 'hermes-gpt55-compact-v0'
SOURCE_STYLE = 'compact-seed'
MAX_SCRATCH_WORDS = 32
MAX_GPT55_SCRATCH_WORDS = 96
MAX_FINAL_WORDS = 80

FORBIDDEN_REASONING_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"here(?:'|’)s a thinking process", re.I),
    re.compile(r'thinking process', re.I),
    re.compile(r'Analyze User Input', re.I),
    re.compile(r'\b\d+\.\s+\*\*Analyze\b', re.I),
    re.compile(r'</?think\b', re.I),
)

GENERIC_REASONING_CUES = (
    'analyze user input',
    "here's a thinking process",
    'thinking process',
    'step-by-step reasoning',
    'chain of thought',
)

UNSAFE_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r'\brm\s+-[A-Za-z]*r[A-Za-z]*f\b'),
    re.compile(r'\bfind\b[^\n;|&]*\s-delete\b'),
    re.compile(r'\bchmod\b'),
    re.compile(r'\bchown\b'),
    re.compile(r'\bmkfs(?:\.[A-Za-z0-9_+-]+)?\b'),
)


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


def _validate_scratch_assistant(content: str, marker: str, max_words: int) -> None:
    try:
        scratch, rest = content.removeprefix(f'{marker}:\n').split('\n\n', 1)
    except ValueError as exc:
        raise UltraCompactViolation(f'{marker} must be followed by blank line and ACTION/FINAL') from exc
    if _word_count(scratch) > max_words:
        raise UltraCompactViolation(f'{marker} scratch exceeds {max_words} words')
    if not (rest.startswith('ACTION ') or rest.startswith('FINAL:')):
        raise UltraCompactViolation(f'{marker} must lead to ACTION or FINAL')


def _assert_no_reasoning_contamination(content: str) -> None:
    for pattern in FORBIDDEN_REASONING_PATTERNS:
        if pattern.search(content):
            raise UltraCompactViolation(f'forbidden reasoning contamination: {pattern.pattern}')


def _assert_not_long_generic_final(content: str) -> None:
    stripped = content.strip()
    if not stripped.startswith('FINAL:'):
        return
    final_text = stripped.removeprefix('FINAL:').strip()
    lowered = final_text.lower()
    if _word_count(final_text) > MAX_FINAL_WORDS:
        raise UltraCompactViolation(f'FINAL exceeds {MAX_FINAL_WORDS} words')
    if any(cue in lowered for cue in GENERIC_REASONING_CUES):
        raise UltraCompactViolation('FINAL contains generic reasoning prose')


def _assert_no_unsafe_action(content: str) -> None:
    for pattern in UNSAFE_ACTION_PATTERNS:
        if pattern.search(content):
            raise UltraCompactViolation(f'unsafe action target: {pattern.pattern}')


def _assert_parseable_action(content: str) -> None:
    stripped = content.strip()
    action = stripped
    if stripped.startswith('SCRATCH<=32:\n'):
        try:
            _, action = stripped.split('\n\n', 1)
        except ValueError as exc:
            raise UltraCompactViolation('SCRATCH<=32 must lead to parseable ACTION/FINAL') from exc
    if not action.startswith('ACTION '):
        return
    match = re.match(r'^ACTION\s+([A-Za-z_][A-Za-z0-9_]*)\s+(\{.*\})$', action.strip(), re.S)
    if not match:
        raise UltraCompactViolation('ACTION must be `ACTION tool {json}`')
    try:
        args = json.loads(match.group(2))
    except json.JSONDecodeError as exc:
        raise UltraCompactViolation(f'ACTION JSON must parse: {exc.msg}') from exc
    if not isinstance(args, dict):
        raise UltraCompactViolation('ACTION args must be a JSON object')


def validate_ultra_compact_assistant(content: str) -> None:
    stripped = content.strip()
    if not stripped:
        raise UltraCompactViolation('assistant content must be non-empty')
    _assert_no_reasoning_contamination(stripped)
    _assert_not_long_generic_final(stripped)
    _assert_no_unsafe_action(stripped)
    _assert_parseable_action(stripped)
    if 'SCRATCH<=80' in stripped or 'SCRATCH<=64' in stripped or 'SCRATCH<=96' in stripped:
        raise UltraCompactViolation('use SCRATCH<=32, ACTION-only, or FINAL-only')

    if stripped.startswith('ACTION '):
        return
    if stripped.startswith('FINAL:'):
        return
    if stripped.startswith('SCRATCH<=32:\n'):
        _validate_scratch_assistant(stripped, 'SCRATCH<=32', MAX_SCRATCH_WORDS)
        return

    raise UltraCompactViolation('assistant must start with ACTION, FINAL:, or SCRATCH<=32')


def validate_gpt55_compact_assistant(content: str) -> None:
    stripped = content.strip()
    if not stripped:
        raise UltraCompactViolation('assistant content must be non-empty')
    _assert_no_reasoning_contamination(stripped)
    _assert_not_long_generic_final(stripped)
    if stripped.startswith('ACTION ') or stripped.startswith('FINAL:'):
        return
    if stripped.startswith('SCRATCH<=96:\n'):
        _validate_scratch_assistant(stripped, 'SCRATCH<=96', MAX_GPT55_SCRATCH_WORDS)
        return
    if stripped.startswith('SCRATCH<=32:\n'):
        _validate_scratch_assistant(stripped, 'SCRATCH<=32', MAX_SCRATCH_WORDS)
        return
    raise UltraCompactViolation('teacher trace must start with ACTION, FINAL:, SCRATCH<=32, or SCRATCH<=96')


def validate_training_assistant(content: str, style: str = STYLE_NAME) -> None:
    if style == GPT55_STYLE_NAME:
        validate_gpt55_compact_assistant(content)
    else:
        validate_ultra_compact_assistant(content)


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


def _classify_output(content: str) -> str:
    stripped = content.strip()
    if stripped.startswith('ACTION '):
        return 'action_only'
    if stripped.startswith('FINAL:'):
        return 'final_only'
    if re.match(r'SCRATCH<=\d+:', stripped):
        _, _, rest = stripped.partition('\n\n')
        if rest.startswith('ACTION '):
            return 'scratch_action'
        if rest.startswith('FINAL:'):
            return 'scratch_final'
    return 'invalid'


def _extract_tool_name(content: str) -> str | None:
    action_match = re.search(r'(?:^|\n)ACTION\s+([A-Za-z_][A-Za-z0-9_]*)\b', content.strip())
    if action_match:
        return action_match.group(1)
    return None


def _scratch_word_count(content: str) -> int:
    stripped = content.strip()
    match = re.match(r'SCRATCH<=\d+:\n(.+?)\n\n', stripped, re.S)
    if not match:
        return 0
    return _word_count(match.group(1))


def summarize_ultra_compact_dataset(rows: Iterable[dict[str, Any]]) -> dict[str, Any]:
    row_list = list(rows)
    by_output_kind: Counter[str] = Counter()
    by_style: Counter[str] = Counter()
    by_tool: Counter[str] = Counter()
    scratch_counts: list[int] = []
    invalid_examples: list[dict[str, Any]] = []

    for index, row in enumerate(row_list, 1):
        try:
            style = row.get('style', STYLE_NAME)
            by_style[style] += 1
            content = _assistant_payload(row)
            validate_training_assistant(content, style)
        except UltraCompactViolation as exc:
            invalid_examples.append({'index': index, 'reason': str(exc)})
            by_output_kind['invalid'] += 1
            continue

        kind = _classify_output(content)
        by_output_kind[kind] += 1
        tool = _extract_tool_name(content)
        if tool:
            by_tool[tool] += 1
        scratch_counts.append(_scratch_word_count(content))

    return {
        'style': 'mixed-hermes-compact-v0' if len(by_style) > 1 else next(iter(by_style), STYLE_NAME),
        'by_style': dict(sorted(by_style.items())),
        'total': len(row_list),
        'by_output_kind': dict(sorted(by_output_kind.items())),
        'by_tool': dict(sorted(by_tool.items())),
        'max_scratch_words': max(scratch_counts, default=0),
        'avg_scratch_words': sum(scratch_counts) / len(scratch_counts) if scratch_counts else 0.0,
        'invalid_examples': invalid_examples,
    }


def validate_quality_gates(
    rows: Iterable[dict[str, Any]],
    *,
    min_examples: int = 30,
    min_action_only: int = 10,
    min_scratch_action: int = 10,
    min_final_only: int = 5,
) -> dict[str, Any]:
    summary = summarize_ultra_compact_dataset(rows)
    if summary['invalid_examples']:
        raise UltraCompactViolation(f"invalid examples: {summary['invalid_examples']}")
    if summary['total'] < min_examples:
        raise UltraCompactViolation(f'dataset must contain at least {min_examples} examples')

    by_kind = summary['by_output_kind']
    requirements = {
        'action_only': min_action_only,
        'scratch_action': min_scratch_action,
        'final_only': min_final_only,
    }
    for kind, minimum in requirements.items():
        actual = by_kind.get(kind, 0)
        if actual < minimum:
            raise UltraCompactViolation(f'{kind} needs at least {minimum} examples, got {actual}')
    if summary['max_scratch_words'] > MAX_GPT55_SCRATCH_WORDS:
        raise UltraCompactViolation(f'scratch exceeds {MAX_GPT55_SCRATCH_WORDS} words')
    return summary


def build_ultra_compact_examples(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[str] = set()
    for path in paths:
        # Validate source schema first so malformed rows fail with precise existing errors.
        load_chat_jsonl(path)
        for row in _read_jsonl(path):
            messages = [dict(message) for message in row['messages']]
            source_style = row.get('style', SOURCE_STYLE)
            last_user_text = ''
            try:
                for message in messages:
                    role = message.get('role')
                    if role == 'user':
                        last_user_text = str(message.get('content', ''))
                    elif role == 'assistant':
                        message['content'] = compress_assistant_content(
                            last_user_text,
                            str(message.get('content', '')),
                        )
                output_style = STYLE_NAME
            except UltraCompactViolation:
                continue
            new_row = {
                **{k: v for k, v in row.items() if k != 'messages'},
                'messages': messages,
                'style': output_style,
                'source_style': source_style,
            }
            fingerprint = json.dumps(new_row['messages'], sort_keys=True, ensure_ascii=False)
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            _assistant_payload(new_row)
            validate_training_assistant(new_row['messages'][-1]['content'], new_row['style'])
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
    parser.add_argument('--report', help='Optional dataset quality report JSON path')
    parser.add_argument('--min-examples', type=int, default=0, help='Fail if fewer examples are produced')
    args = parser.parse_args()

    rows = build_ultra_compact_examples(args.input)
    if args.min_examples:
        summary = validate_quality_gates(rows, min_examples=args.min_examples)
    else:
        summary = summarize_ultra_compact_dataset(rows)
    write_jsonl(args.output, rows)
    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'output': args.output, 'examples': len(rows), 'style': summary['style']}, indent=2))


if __name__ == '__main__':
    main()
