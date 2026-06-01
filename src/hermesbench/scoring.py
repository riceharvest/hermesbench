from __future__ import annotations
import json, statistics
from pathlib import Path
from .schemas import validate_result_schema

def aggregate(path: str | Path) -> dict:
    data=json.loads(Path(path).read_text()); validate_result_schema(data)
    rs=data['results']; n=len(rs) or 1
    cats={}
    for r in rs: cats.setdefault(r['category'], []).append(r)
    def avg(xs): return sum(x['score'] for x in xs)/len(xs) if xs else 0
    successes=[r for r in rs if r.get('passed')]
    cost_success=None
    costs=[r.get('cost_usd') for r in successes if r.get('cost_usd') is not None]
    if costs: cost_success=sum(costs)/len(successes)
    return {
      'schema_version':'hermesbench.score.v1',
      'run_id':data['run_id'], 'agent':data['agent'], 'model':data.get('model'), 'suite':data['suite'],
      'provider':data.get('metadata',{}).get('provider'), 'reasoning_effort':data.get('metadata',{}).get('reasoning_effort'),
      'overall_score':avg(rs), 'pass_at_1':sum(1 for r in rs if r.get('passed'))/n,
      'category_scores':{k:avg(v) for k,v in sorted(cats.items())},
      'cost_per_successful_task_usd':cost_success,
      'median_wall_time_seconds':statistics.median([r['wall_time_seconds'] for r in rs]) if rs else 0,
      'tool_call_count':sum(r.get('tool_calls',0) for r in rs),
      'verification_compliance':sum(1 for r in rs if r.get('verification_evidence'))/n,
      'false_done_rate':sum(1 for r in rs if r.get('false_done'))/n,
      'timeout_rate':sum(1 for r in rs if r.get('timeout'))/n,
      'task_count':len(rs),
    }
