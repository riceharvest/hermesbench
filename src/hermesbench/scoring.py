from __future__ import annotations
import json, statistics
from datetime import datetime, timezone
from pathlib import Path
from .schemas import validate_result_schema


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


def _parse_iso_timestamp(s: str) -> datetime | None:
    """Try to parse an ISO-8601 timestamp string; return None on failure.

    Z-suffixed timestamps (e.g. ``2026-07-10T00:00:00Z``) are returned as
    timezone-aware UTC datetimes.  This ensures they can be safely subtracted
    from other aware datetimes (e.g. timestamps with ``+00:00`` offsets) in
    :func:`_run_duration_seconds` without raising ``TypeError``.
    """
    if not s or not isinstance(s, str):
        return None
    had_z = s.endswith("Z")
    stripped = s.rstrip("Z")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
    ):
        try:
            dt = datetime.strptime(stripped, fmt)
            if had_z:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _run_duration_seconds(started_at: str, completed_at: str) -> float | None:
    """Wall-clock duration of the whole run, or None if timestamps aren't parseable."""
    start = _parse_iso_timestamp(started_at)
    end = _parse_iso_timestamp(completed_at)
    if start is not None and end is not None:
        return (end - start).total_seconds()
    return None


# ── Canonical token-usage field names ────────────────────────────────────────
# These are the explicit, well-known token categories we try to aggregate.
# Each maps to one or more possible keys found in token_usage dicts.
_TOKEN_KEYS: dict[str, tuple[str, ...]] = {
    "prompt_tokens": ("prompt_tokens", "input_tokens"),
    "cached_prompt_tokens": ("cached_prompt_tokens", "cached_input_tokens", "prompt_tokens_cached"),
    "completion_tokens": ("completion_tokens", "output_tokens"),
    "reasoning_tokens": ("reasoning_tokens", "reasoning_output_tokens"),
    "tool_call_tokens": ("tool_call_tokens", "tool_use_tokens"),
    "total_tokens": ("total_tokens",),
}

# Token-availability / source fields we aggregate when present.
_TOKEN_META_KEYS: tuple[str, ...] = (
    "input_tokens_cache_read",
    "input_tokens_cache_write",
    "token_source",
)


def _aggregate_token_field(rs: list[dict], canonical_name: str, aliases: tuple[str, ...]) -> float | None:
    """Sum a token field across all results, trying aliases in order.

    Returns None if *no* result has any of the aliases (missing data stays null).
    Returns 0 if results have the field but all values are zero.
    """
    total = 0
    found = False
    for r in rs:
        usage = r.get("token_usage") or {}
        if not isinstance(usage, dict):
            continue
        val = None
        for alias in aliases:
            v = usage.get(alias)
            if v is not None and isinstance(v, (int, float)):
                val = v
                break
        if val is not None:
            total += val
            found = True
    return total if found else None


def _aggregate_token_meta(rs: list[dict], key: str) -> float | None:
    """Sum a token-meta field across results; None if entirely absent."""
    total = 0
    found = False
    for r in rs:
        usage = r.get("token_usage") or {}
        if not isinstance(usage, dict):
            continue
        v = usage.get(key)
        if v is not None and isinstance(v, (int, float)):
            total += v
            found = True
    return total if found else None


def _aggregate_token_source(rs: list[dict]) -> list[str] | None:
    """Collect unique token_source string values across results.

    Returns a sorted list of unique string sources, or None if *no* result
    has a ``token_source`` field with a non-empty string or list value.
    Supports both individual string values and lists of strings (in case a
    task uses multiple tokenisation back-ends).
    """
    seen: set[str] = set()
    for r in rs:
        usage = r.get("token_usage") or {}
        if not isinstance(usage, dict):
            continue
        raw = usage.get("token_source")
        if raw is None:
            continue
        if isinstance(raw, str) and raw:
            seen.add(raw)
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item:
                    seen.add(item)
    return sorted(seen) if seen else None


def aggregate(path: str | Path) -> dict:
    data=json.loads(Path(path).read_text()); validate_result_schema(data)
    all_results=data['results']
    rs=[r for r in all_results if not r.get('environment_skip')]
    attempted=all_results
    n=len(rs) or 1
    cats={}
    tiers={}
    for r in rs:
        cats.setdefault(r['category'], []).append(r)
        tiers.setdefault(r.get('task_quality_tier') or 'unknown', []).append(r)
    def raw_score(r): return float(r.get('raw_task_score', r.get('score') or 0) or 0)
    def effective_score(r): return float(r.get('effective_task_score', 0.0 if r.get('false_done') else r.get('score') or 0) or 0)
    def total(xs): return sum(effective_score(x) for x in xs)
    def raw_total(xs): return sum(raw_score(x) for x in xs)
    def avg(xs): return total(xs)/len(xs) if xs else 0
    def raw_avg(xs): return raw_total(xs)/len(xs) if xs else 0
    successes=[r for r in rs if r.get('passed')]
    costs=[r.get('cost_usd') for r in attempted if r.get('cost_usd') is not None]
    success_costs=[r.get('cost_usd') for r in successes if r.get('cost_usd') is not None]
    total_cost=sum(costs) if costs else None
    cost_success=sum(success_costs)/len(successes) if success_costs and successes else None
    cost_coverage=len(costs)/len(attempted) if attempted else 0.0
    cost_status=(
        'unavailable' if not costs else
        ('partial' if len(costs) < len(attempted) else
         ('complete_zero' if sum(costs) == 0 else 'complete'))
    )
    runtime_warning_results=[r for r in attempted if r.get('runtime_issues')]
    runtime_warnings=sorted({
        issue for r in runtime_warning_results for issue in r.get('runtime_issues', [])
    })

    # ── Full token aggregation ───────────────────────────────────────────
    token_usage={}
    for r in attempted:
        usage=r.get('token_usage') or {}
        if isinstance(usage, dict):
            for k,v in usage.items():
                if isinstance(v, (int, float)):
                    token_usage[k]=token_usage.get(k,0)+v

    # Backward-compat total_tokens, input_tokens, output_tokens
    total_tokens=token_usage.get('total_tokens')
    if total_tokens is None:
        total_tokens=sum(v for k,v in token_usage.items() if isinstance(v, (int, float)) and 'token' in k and k != 'total_tokens') or None
    input_tokens=token_usage.get('input_tokens') or token_usage.get('prompt_tokens')
    output_tokens=token_usage.get('output_tokens') or token_usage.get('completion_tokens')

    # Explicit field-by-field aggregation (null-safe)
    prompt_tokens = _aggregate_token_field(attempted, "prompt_tokens", _TOKEN_KEYS["prompt_tokens"])
    cached_prompt_tokens = _aggregate_token_field(attempted, "cached_prompt_tokens", _TOKEN_KEYS["cached_prompt_tokens"])
    completion_tokens = _aggregate_token_field(attempted, "completion_tokens", _TOKEN_KEYS["completion_tokens"])
    reasoning_tokens = _aggregate_token_field(attempted, "reasoning_tokens", _TOKEN_KEYS["reasoning_tokens"])
    tool_call_tokens = _aggregate_token_field(attempted, "tool_call_tokens", _TOKEN_KEYS["tool_call_tokens"])
    explicit_total_tokens = _aggregate_token_field(attempted, "total_tokens", _TOKEN_KEYS["total_tokens"])

    # Token availability/source
    input_tokens_cache_read = _aggregate_token_meta(attempted, "input_tokens_cache_read")
    input_tokens_cache_write = _aggregate_token_meta(attempted, "input_tokens_cache_write")
    token_source = _aggregate_token_source(attempted)

    # ── Run duration ─────────────────────────────────────────────────────
    run_duration = _run_duration_seconds(data.get("started_at", ""), data.get("completed_at", ""))

    # ── Wall time stats (preserve existing, add sum) ─────────────────────
    wall_times=[float(r['wall_time_seconds']) for r in attempted]

    # ── Throughput ───────────────────────────────────────────────────────
    # tasks_per_second: only when run_duration is available
    tasks_per_second = len(attempted) / run_duration if attempted and run_duration is not None and run_duration > 0 else None
    # tokens_per_second: only when both run_duration and total_tokens are available
    tokens_per_second = total_tokens / run_duration if run_duration is not None and run_duration > 0 and total_tokens is not None else None

    tool_call_count=sum(r.get('tool_calls', r.get('tool_call_count',0)) for r in attempted)
    total_score=total(rs)
    raw_total_score=raw_total(rs)
    max_score=len(rs)
    score_percentage=total_score/max_score if max_score else 0
    false_done_rate=sum(1 for r in rs if r.get('false_done'))/n
    timeout_rate=sum(1 for r in rs if r.get('timeout'))/n
    endurance_score=max(0.0, score_percentage * (1.0 - false_done_rate) * (1.0 - timeout_rate))

    return {
      'schema_version':'hermesbench.score.v1',
      'run_id':data['run_id'], 'agent':data['agent'], 'model':data.get('model'), 'suite':data['suite'],
      'provider':data.get('metadata',{}).get('provider'), 'reasoning_effort':data.get('metadata',{}).get('reasoning_effort'),
      'overall_score':score_percentage, 'raw_overall_score': raw_total_score/max_score if max_score else 0, 'pass_at_1':sum(1 for r in rs if r.get('passed'))/n,
      'score_percentage': score_percentage, 'total_score': total_score, 'raw_total_score': raw_total_score, 'max_score': max_score,
      'category_scores':{k:avg(v) for k,v in sorted(cats.items())},
      'raw_category_scores':{k:raw_avg(v) for k,v in sorted(cats.items())},
      'quality_tier_scores':{k:avg(v) for k,v in sorted(tiers.items())},
      'raw_quality_tier_scores':{k:raw_avg(v) for k,v in sorted(tiers.items())},
      'quality_tier_counts':{k:len(v) for k,v in sorted(tiers.items())},
      'task_count':len(all_results), 'scored_task_count':len(rs),
      'environment_skip_count':sum(1 for r in all_results if r.get('environment_skip')),
      'passed_task_count':len(successes), 'failed_task_count':sum(1 for r in rs if not r.get('passed')),
      'cost_per_successful_task_usd':cost_success,
      'cost_per_task_usd': total_cost/len(attempted) if total_cost is not None and attempted else None,
      'cost_usd':total_cost, 'total_cost_usd': total_cost,
      'cost_telemetry_task_count': len(costs),
      'cost_telemetry_coverage': cost_coverage,
      'cost_telemetry_status': cost_status,
      'score_per_dollar': (score_percentage * 100 / total_cost) if total_cost and total_cost > 0 else None,
      'token_usage':token_usage or None,
      'input_tokens': input_tokens, 'output_tokens': output_tokens,
      'total_tokens':total_tokens,
      # ── Explicit per-field token aggregates ────────────────────────────
      'prompt_tokens': prompt_tokens,
      'cached_prompt_tokens': cached_prompt_tokens,
      'completion_tokens': completion_tokens,
      'reasoning_tokens': reasoning_tokens,
      'tool_call_tokens': tool_call_tokens,
      'explicit_total_tokens': explicit_total_tokens,
      'input_tokens_cache_read': input_tokens_cache_read,
      'input_tokens_cache_write': input_tokens_cache_write,
      'token_source': token_source,
      # ── Per-task token averages ────────────────────────────────────────
      'tokens_per_task': total_tokens/len(attempted) if total_tokens is not None and attempted else None,
      'tokens_per_successful_task': total_tokens/len(successes) if total_tokens is not None and successes else None,
      'prompt_tokens_per_task': prompt_tokens/len(attempted) if prompt_tokens is not None and attempted else None,
      'completion_tokens_per_task': completion_tokens/len(attempted) if completion_tokens is not None and attempted else None,
      'reasoning_tokens_per_task': reasoning_tokens/len(attempted) if reasoning_tokens is not None and attempted else None,
      'tool_call_tokens_per_task': tool_call_tokens/len(attempted) if tool_call_tokens is not None and attempted else None,
      # ── Wall-clock run duration ────────────────────────────────────────
      'run_duration_seconds': run_duration,
      'total_execution_time_seconds': sum(wall_times),
      'sum_wall_time_seconds': sum(wall_times),
      'median_wall_time_seconds': statistics.median(wall_times) if wall_times else None,
      'mean_wall_time_seconds': statistics.mean(wall_times) if wall_times else None,
      'min_wall_time_seconds': min(wall_times) if wall_times else None,
      'max_wall_time_seconds': max(wall_times) if wall_times else None,
      'p95_wall_time_seconds': _percentile(wall_times, 95),
      # ── Throughput ─────────────────────────────────────────────────────
      'tasks_per_second': tasks_per_second,
      'tokens_per_second': tokens_per_second,
      # ── Tool calls ─────────────────────────────────────────────────────
      'tool_call_count':tool_call_count,
      'avg_tool_calls_per_task': tool_call_count/len(attempted) if attempted else 0,
      'verification_compliance':sum(1 for r in rs if r.get('verification_evidence'))/n,
      'false_done_count': sum(1 for r in rs if r.get('false_done')),
      'false_done_rate':false_done_rate,
      'timeout_count': sum(1 for r in rs if r.get('timeout')),
      'timeout_rate':timeout_rate,
      'runtime_warning_task_count': len(runtime_warning_results),
      'runtime_warnings': runtime_warnings,

      'tool_use_behavior': {
        'tasks_with_tool_use_requirements': sum(1 for r in rs if _extract_required_tool_classes(r)),
        'tool_use_tasks_passed': sum(1 for r in rs if _extract_required_tool_classes(r) and _extract_required_tool_classes(r).issubset(_extract_used_tool_classes(r))),
        'tool_use_pass_rate': sum(1 for r in rs if _extract_required_tool_classes(r) and _extract_required_tool_classes(r).issubset(_extract_used_tool_classes(r))) / max(1, sum(1 for r in rs if _extract_required_tool_classes(r))),
        'tool_classes_used': sorted({cls for r in rs for cls in _extract_used_tool_classes(r)}),
        'tool_classes_required': sorted({cls for r in rs for cls in _extract_required_tool_classes(r)}),
      },
      'capability_evaluable': not any(
          r.get('environment_skip') and _extract_required_tool_classes(r)
          for r in all_results
      ),
      'capability_pass': is_capability_pass({'results': all_results}),
      'tool_capability_evaluable': not any(
          r.get('environment_skip') and _extract_required_tool_classes(r)
          for r in all_results
      ),
      'tool_capability_pass': is_tool_capability_pass({'results': all_results}),
      'task_correctness_pass': bool(rs) and len(successes) == len(rs) and len(rs) == len(all_results),
    }


def _extract_used_tool_classes(r: dict) -> set[str]:
    """Return the tool classes the agent actually invoked according to telemetry."""
    return set(r.get('tool_classes_used') or [])


def _extract_required_tool_classes(r: dict) -> set[str]:
    """Return the tool classes declared as required by the task."""
    return set(r.get('required_tool_classes') or [])


def is_capability_pass(score_or_result: dict) -> bool:
    """Return True iff every required tool class was used in every task that has requirements.

    This is the core minimum-capable-model boundary check.
    """
    rs = score_or_result.get('results')
    if rs is None:
        # Aggregate union sets cannot prove that each task satisfied its own
        # requirements. Reuse the task-scoped result computed by aggregate().
        return bool(score_or_result.get('capability_pass', False))
    saw_requirement = False
    for r in rs:
        if r.get('environment_skip'):
            if _extract_required_tool_classes(r):
                return False
            continue
        used = _extract_used_tool_classes(r)
        required = _extract_required_tool_classes(r)
        saw_requirement = saw_requirement or bool(required)
        if required and (not r.get('passed') or r.get('false_done') or r.get('timeout') or not required.issubset(used)):
            return False
    return saw_requirement


def is_tool_capability_pass(score_or_result: dict) -> bool:
    """Return True iff every evaluable task invoked its required tool classes."""
    rs = score_or_result.get('results')
    if rs is None:
        return bool(score_or_result.get('tool_capability_pass', False))
    saw_requirement = False
    for r in rs:
        required = _extract_required_tool_classes(r)
        if r.get('environment_skip') and required:
            return False
        saw_requirement = saw_requirement or bool(required)
        if required and not required.issubset(_extract_used_tool_classes(r)):
            return False
    return saw_requirement
