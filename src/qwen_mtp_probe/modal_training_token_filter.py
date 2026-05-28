from __future__ import annotations

from typing import Any


def filter_tokenized_examples_by_length(
    rows: list[dict[str, Any]],
    *,
    max_tokens: int | None,
) -> tuple[list[dict[str, Any]], dict[str, int | None]]:
    if max_tokens is None:
        kept = rows
    else:
        kept = [row for row in rows if len(row.get('input_ids', [])) <= max_tokens]

    return kept, {
        'before': len(rows),
        'after': len(kept),
        'dropped_over_token_budget': len(rows) - len(kept),
        'max_train_tokens': max_tokens,
    }
