from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from qwen_mtp_probe.eval_usecase import score_output


class SelectedSmokeEvalItems(list[dict[str, Any]]):
    def __init__(self, items: list[dict[str, Any]]) -> None:
        super().__init__(items)
        self.scorer_counts = dict(Counter(str(item['scorer']) for item in items))


def _valid_smoke_eval_row(row: dict[str, Any]) -> bool:
    return (
        isinstance(row.get('id'), str)
        and isinstance(row.get('input'), str)
        and bool(row['input'].strip())
        and isinstance(row.get('scorer'), str)
        and bool(row['scorer'].strip())
    )


def select_smoke_eval_items(rows: list[dict[str, Any]], *, limit: int) -> SelectedSmokeEvalItems:
    """Select a scorer-balanced held-out smoke slice.

    Eval files are grouped by scorer, so a naive first-N slice mostly tests one behavior.
    Round-robin through scorer buckets to exercise tool choice, repo inspection,
    verification, concise finals, clarification restraint, and style in the same GPU smoke.
    """
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    scorer_order: list[str] = []
    for row in rows:
        if not _valid_smoke_eval_row(row):
            continue
        scorer = str(row['scorer'])
        if scorer not in buckets:
            scorer_order.append(scorer)
        buckets[scorer].append(row)

    selected: list[dict[str, Any]] = []
    index = 0
    while len(selected) < limit:
        added_this_round = False
        for scorer in scorer_order:
            bucket = buckets[scorer]
            if index < len(bucket):
                selected.append(bucket[index])
                added_this_round = True
                if len(selected) >= limit:
                    break
        if not added_this_round:
            break
        index += 1
    return SelectedSmokeEvalItems(selected)


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
