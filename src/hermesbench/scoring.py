from __future__ import annotations
import json, statistics
from pathlib import Path
from .schemas import validate_result_schema


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round((pct / 100) * (len(ordered) - 1))))
    return ordered[idx]


def aggregate(path: str | Path) -> dict:
    data=json.loads(Path(path).read_text()); validate_result_schema(data)
    rs=data['results']; n=len(rs) or 1
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
    costs=[r.get('cost_usd') for r in rs if r.get('cost_usd') is not None]
    success_costs=[r.get('cost_usd') for r in successes if r.get('cost_usd') is not None]
    total_cost=sum(costs) if costs else None
    cost_success=sum(success_costs)/len(successes) if success_costs and successes else None
    token_usage={}
    for r in rs:
        usage=r.get('token_usage') or {}
        if isinstance(usage, dict):
            for k,v in usage.items():
                if isinstance(v, (int, float)):
                    token_usage[k]=token_usage.get(k,0)+v
    total_tokens=token_usage.get('total_tokens')
    if total_tokens is None:
        total_tokens=sum(v for k,v in token_usage.items() if isinstance(v, (int, float)) and 'token' in k and k != 'total_tokens') or None
    input_tokens=token_usage.get('input_tokens') or token_usage.get('prompt_tokens')
    output_tokens=token_usage.get('output_tokens') or token_usage.get('completion_tokens')
    wall_times=[float(r['wall_time_seconds']) for r in rs]
    tool_call_count=sum(r.get('tool_calls', r.get('tool_call_count',0)) for r in rs)
    total_score=total(rs)
    raw_total_score=raw_total(rs)
    max_score=len(rs)
    score_percentage=total_score/max_score if max_score else 0
    false_done_rate=sum(1 for r in rs if r.get('false_done'))/n
    timeout_rate=sum(1 for r in rs if r.get('timeout'))/n
    endurance_score=max(0.0, score_percentage * (1.0 - false_done_rate) * (1.0 - timeout_rate))
    long_horizon_metrics={
      'endurance_score': endurance_score,
      'stage_completion_proxy': raw_total_score/max_score if max_score else 0,
      'false_done_resistance': 1.0 - false_done_rate,
      'timeout_resistance': 1.0 - timeout_rate,
      'median_task_minutes': (statistics.median(wall_times)/60) if wall_times else 0,
      'p95_task_minutes': ((_percentile(wall_times, 95) or 0)/60),
    } if str(data.get('suite','')).startswith('long-horizon') else None
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
      'task_count':len(rs), 'passed_task_count':len(successes), 'failed_task_count':sum(1 for r in rs if not r.get('passed')),
      'cost_per_successful_task_usd':cost_success,
      'cost_per_task_usd': total_cost/len(rs) if total_cost is not None and rs else None,
      'cost_usd':total_cost, 'total_cost_usd': total_cost,
      'score_per_dollar': (score_percentage * 100 / total_cost) if total_cost and total_cost > 0 else None,
      'token_usage':token_usage or None,
      'input_tokens': input_tokens, 'output_tokens': output_tokens,
      'total_tokens':total_tokens,
      'tokens_per_task': total_tokens/len(rs) if total_tokens and rs else None,
      'tokens_per_successful_task': total_tokens/len(successes) if total_tokens and successes else None,
      'total_execution_time_seconds': sum(wall_times),
      'median_wall_time_seconds':statistics.median(wall_times) if wall_times else 0,
      'mean_wall_time_seconds':statistics.mean(wall_times) if wall_times else 0,
      'min_wall_time_seconds':min(wall_times) if wall_times else 0,
      'max_wall_time_seconds':max(wall_times) if wall_times else 0,
      'p95_wall_time_seconds':_percentile(wall_times, 95) or 0,
      'tool_call_count':tool_call_count,
      'avg_tool_calls_per_task': tool_call_count/len(rs) if rs else 0,
      'verification_compliance':sum(1 for r in rs if r.get('verification_evidence'))/n,
      'false_done_count': sum(1 for r in rs if r.get('false_done')),
      'false_done_rate':false_done_rate,
      'timeout_count': sum(1 for r in rs if r.get('timeout')),
      'timeout_rate':timeout_rate,
      'long_horizon_metrics': long_horizon_metrics,
    }
