from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ALLOWED_ROLES = {'system', 'user', 'assistant', 'tool'}
EVAL_REQUIRED_KEYS = {'id', 'input', 'expected_behavior', 'scorer'}


@dataclass(frozen=True)
class ChatMessage:
    role: str
    content: str


@dataclass(frozen=True)
class ChatExample:
    messages: list[ChatMessage]
    metadata: dict[str, Any]


@dataclass(frozen=True)
class EvalItem:
    id: str
    input: str
    expected_behavior: str
    scorer: str
    metadata: dict[str, Any]


def _coerce_path(path: str | Path) -> Path:
    return path if isinstance(path, Path) else Path(path)


def _read_jsonl(path: str | Path) -> list[dict[str, Any]]:
    p = _coerce_path(path)
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


def load_chat_jsonl(path: str | Path) -> list[ChatExample]:
    examples: list[ChatExample] = []
    for index, row in enumerate(_read_jsonl(path), 1):
        raw_messages = row.get('messages')
        if not isinstance(raw_messages, list) or not raw_messages:
            raise ValueError(f'row {index}: messages must be a non-empty list')
        messages: list[ChatMessage] = []
        for message_index, raw_message in enumerate(raw_messages, 1):
            if not isinstance(raw_message, dict):
                raise ValueError(f'row {index} message {message_index}: expected object')
            role = raw_message.get('role')
            content = raw_message.get('content')
            if role not in ALLOWED_ROLES:
                raise ValueError(f'row {index} message {message_index}: invalid role {role!r}')
            if not isinstance(content, str) or not content.strip():
                raise ValueError(f'row {index} message {message_index}: content must be non-empty')
            messages.append(ChatMessage(role=role, content=content))
        if messages[-1].role != 'assistant':
            raise ValueError(f'row {index}: last message must be assistant')
        examples.append(
            ChatExample(
                messages=messages,
                metadata={k: v for k, v in row.items() if k != 'messages'},
            )
        )
    return examples


def load_eval_jsonl(path: str | Path) -> list[EvalItem]:
    items: list[EvalItem] = []
    for index, row in enumerate(_read_jsonl(path), 1):
        missing = sorted(EVAL_REQUIRED_KEYS - set(row))
        if missing:
            raise ValueError(f'row {index}: missing required eval keys: {", ".join(missing)}')
        for key in EVAL_REQUIRED_KEYS:
            if not isinstance(row[key], str) or not row[key].strip():
                raise ValueError(f'row {index}: {key} must be a non-empty string')
        items.append(
            EvalItem(
                id=row['id'],
                input=row['input'],
                expected_behavior=row['expected_behavior'],
                scorer=row['scorer'],
                metadata={k: v for k, v in row.items() if k not in EVAL_REQUIRED_KEYS},
            )
        )
    return items
