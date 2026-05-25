from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ScoreResult:
    scorer: str
    passed: bool
    reason: str
    details: dict[str, Any]


def _word_count(text: str) -> int:
    return len(re.findall(r'\S+', text))


def _has_action(text: str) -> bool:
    lowered = text.lower()
    return 'action ' in lowered or '\naction' in lowered or lowered.strip().startswith('action')


def score_output(scorer: str, output: str, *, max_words: int = 120) -> ScoreResult:
    text = output.strip()
    lowered = text.lower()

    if scorer == 'tool_use_required':
        passed = _has_action(text)
        return ScoreResult(scorer, passed, 'requires parseable ACTION marker', {'has_action': passed})

    if scorer == 'repo_inspection_required':
        markers = ['search_files', 'read_file', 'git ', 'git status', 'ls ', 'find ']
        passed = any(marker in lowered for marker in markers)
        return ScoreResult(scorer, passed, 'requires file/repo inspection before answer', {'markers': markers})

    if scorer == 'verification_required':
        markers = ['verified', 'tests pass', 'report shows', 'error=null', 'exit_code": 0', 'exit code 0']
        passed = any(marker in lowered for marker in markers)
        return ScoreResult(scorer, passed, 'requires verification evidence', {'markers': markers})

    if scorer == 'concise_final_required':
        words = _word_count(text)
        passed = words <= max_words
        return ScoreResult(scorer, passed, f'requires <= {max_words} words', {'words': words, 'max_words': max_words})

    if scorer == 'no_unnecessary_clarification':
        question_count = text.count('?')
        passed = question_count == 0 or _has_action(text)
        return ScoreResult(
            scorer,
            passed,
            'question-only clarification is disallowed when action is obvious',
            {'question_count': question_count, 'has_action': _has_action(text)},
        )

    raise ValueError(f'unknown scorer: {scorer}')


def summarize_scores(scores: list[ScoreResult]) -> dict[str, Any]:
    total = len(scores)
    passed = sum(1 for score in scores if score.passed)
    by_scorer: dict[str, dict[str, int]] = {}
    for score in scores:
        bucket = by_scorer.setdefault(score.scorer, {'total': 0, 'passed': 0})
        bucket['total'] += 1
        bucket['passed'] += int(score.passed)
    return {
        'total': total,
        'passed': passed,
        'failed': total - passed,
        'pass_rate': passed / total if total else None,
        'by_scorer': by_scorer,
    }
