from __future__ import annotations

from typing import Any

from qwen_mtp_probe.eval_usecase import score_output


def select_smoke_eval_items(rows: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row.get('id'), str):
            continue
        if not isinstance(row.get('input'), str) or not row['input'].strip():
            continue
        if not isinstance(row.get('scorer'), str) or not row['scorer'].strip():
            continue
        selected.append(row)
        if len(selected) >= limit:
            break
    return selected


def evaluate_smoke_generations(
    items: list[dict[str, Any]],
    generations: dict[str, str],
) -> dict[str, Any]:
    scored_items: list[dict[str, Any]] = []
    passed = 0
    for item in items:
        item_id = str(item['id'])
        output = generations.get(item_id, '')
        task_score = score_output(str(item['scorer']), output)
        style_score = score_output('ultra_compact_style', output)
        item_passed = task_score.passed and style_score.passed
        passed += int(item_passed)
        scored_items.append(
            {
                'id': item_id,
                'input': item['input'],
                'scorer': item['scorer'],
                'output': output,
                'passed': item_passed,
                'task_passed': task_score.passed,
                'task_reason': task_score.reason,
                'style_passed': style_score.passed,
                'style_reason': style_score.reason,
            }
        )
    total = len(scored_items)
    return {
        'total': total,
        'passed': passed,
        'failed': total - passed,
        'pass_rate': passed / total if total else None,
        'items': scored_items,
    }
