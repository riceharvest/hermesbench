from __future__ import annotations
import argparse, json, math, re, statistics
from pathlib import Path
from hermesbench.scoring import aggregate

ROOT = Path(__file__).resolve().parents[1]

def _model_key(entry: dict) -> tuple[str, str, str, str, bool]:
    return (entry.get('agent') or '', entry.get('provider') or '', entry.get('model') or '', entry.get('reasoning_effort') or '', bool(entry.get('official')))

def _slug(s: str) -> str:
    return re.sub(r'[^a-z0-9]+', '-', (s or 'unknown').lower()).strip('-')

def _enhance(entry: dict) -> dict:
    score = float(entry.get('score_percentage', entry.get('overall_score', 0)) or 0)
    false_done = float(entry.get('false_done_rate') or 0)
    timeout = float(entry.get('timeout_rate') or 0)
    reliability = max(0.0, min(1.0, 1.0 - ((false_done * 0.65) + (timeout * 0.35))))
    total_tokens = entry.get('total_tokens')
    token_efficiency = (score / total_tokens * 1_000_000) if total_tokens else None
    cost = entry.get('total_cost_usd', entry.get('cost_usd'))
    value_score = (score / cost) if cost else None
    cpst = None
    if cost is not None and entry.get('passed_task_count'):
        cpst = cost / entry['passed_task_count']
    return {**entry, 'reliability_score': reliability, 'token_efficiency_score': token_efficiency, 'value_score': value_score, 'cpst': cpst, 'model_slug': _slug(f"{entry.get('provider','')}-{entry.get('model','')}-{entry.get('reasoning_effort','')}")}

def _summarize_group(rows: list[dict]) -> dict:
    best = max(rows, key=lambda e: (e.get('score_percentage', e.get('overall_score', 0)), e.get('pass_at_1', 0)))
    scores = [float(e.get('score_percentage', e.get('overall_score', 0)) or 0) for e in rows]
    avg = statistics.mean(scores) if scores else 0
    std = statistics.stdev(scores) if len(scores) > 1 else 0.0
    ci = 1.96 * std / math.sqrt(len(scores)) if len(scores) > 1 else 0.0
    nums = lambda k: [e.get(k) for e in rows if e.get(k) is not None]
    costs = [e.get('total_cost_usd', e.get('cost_usd')) for e in rows if e.get('total_cost_usd', e.get('cost_usd')) is not None]
    agent, provider, model, reasoning, official = _model_key(best)
    out = {
        'agent': agent, 'provider': provider or None, 'model': model or None, 'reasoning_effort': reasoning or None,
        'official': official, 'classification': 'official' if official else 'unofficial', 'submission_count': len(rows),
        'best_submission_id': best.get('run_id'), 'best_score_percentage': max(scores) if scores else 0, 'average_score_percentage': avg,
        'score_stddev': std, 'score_ci95_low': max(0, avg - ci), 'score_ci95_high': min(1, avg + ci),
        'average_pass_at_1': statistics.mean(nums('pass_at_1') or [0]),
        'average_false_done_rate': statistics.mean(nums('false_done_rate') or [0]),
        'average_timeout_rate': statistics.mean(nums('timeout_rate') or [0]),
        'average_cost_usd': statistics.mean(costs) if costs else None,
        'average_execution_time_seconds': statistics.mean(nums('total_execution_time_seconds')) if nums('total_execution_time_seconds') else None,
        'average_total_tokens': statistics.mean(nums('total_tokens')) if nums('total_tokens') else None,
        'average_tool_call_count': statistics.mean(nums('tool_call_count')) if nums('tool_call_count') else None,
        'best_raw_score_percentage': best.get('raw_overall_score'), 'best_passed_task_count': best.get('passed_task_count'),
        'best_failed_task_count': best.get('failed_task_count'), 'best_task_count': best.get('task_count'),
        'best_false_done_count': best.get('false_done_count'), 'best_timeout_count': best.get('timeout_count'),
        'best_median_wall_time_seconds': best.get('median_wall_time_seconds'), 'best_p95_wall_time_seconds': best.get('p95_wall_time_seconds'),
        'best_tokens_per_successful_task': best.get('tokens_per_successful_task'), 'best_verification_compliance': best.get('verification_compliance'),
        'source': best.get('source'), 'run_id': best.get('run_id'),
    }
    return _enhance(out)

def _task_detail(task: dict) -> dict:
    evidence = task.get('verification_evidence') or []
    checks = []
    for item in evidence:
        status = 'pass' if ': PASS' in item else 'fail' if ': FAIL' in item else 'info'
        checks.append({'label': item.replace(': PASS','').replace(': FAIL',''), 'status': status})
    return {**task, 'max_score': task.get('max_score', 1), 'checks': checks, 'grading_type': task.get('grading_type') or task.get('category') or 'deterministic'}

def build_data(results_dir: Path = ROOT / 'results', out_dir: Path = ROOT / 'website' / 'data') -> tuple[Path, Path]:
    entries=[]; details=[]
    runs_dir = out_dir / 'runs'
    runs_dir.mkdir(parents=True, exist_ok=True)
    for old in runs_dir.glob('*.json'):
        old.unlink()
    for result_path in sorted(results_dir.glob('**/hermesbench-*.json')):
        data=json.loads(result_path.read_text())
        score=aggregate(result_path)
        official=bool(data.get('metadata', {}).get('official'))
        source=str(result_path.relative_to(ROOT)) if result_path.is_relative_to(ROOT) else str(result_path)
        entry=_enhance({**score,'official':official,'classification':'official' if official else 'unofficial','source':source})
        tasks=[_task_detail(t) for t in data.get('results',[])]
        detail={**entry,'tasks':tasks,'raw_result_schema_version':data.get('schema_version'),'started_at':data.get('started_at'),'completed_at':data.get('completed_at'),'metadata':data.get('metadata',{})}
        entries.append(entry); details.append(detail)
        (runs_dir / f"{entry['run_id']}.json").write_text(json.dumps(detail,indent=2,sort_keys=True))
    entries.sort(key=lambda e: (not e['official'], -e['overall_score'], e['run_id']))
    for i,e in enumerate([e for e in entries if e['official']],1): e['rank']=i
    for i,e in enumerate([e for e in entries if not e['official']],1): e['rank']=i
    groups: dict[tuple[str, str, str, str, bool], list[dict]] = {}
    for entry in entries: groups.setdefault(_model_key(entry), []).append(entry)
    summaries=sorted((_summarize_group(rows) for rows in groups.values()), key=lambda e: (not e['official'], -e['average_score_percentage'], -(e['submission_count'])))
    payload={'schema_version':'hermesbench.website.leaderboard.v3','generated_from':'committed results/ files','metric_notes':'Public-dev rows are single-run samples unless grouped by repeated runs; official rankings require maintainer private/fresh packs.','official':[e for e in entries if e['official']],'unofficial':[e for e in entries if not e['official']],'model_summaries':summaries,'entries':entries}
    out_dir.mkdir(parents=True, exist_ok=True)
    lb=out_dir/'leaderboard.json'; lb.write_text(json.dumps(payload,indent=2,sort_keys=True))
    demo=out_dir/'latest-result.json'; demo.write_text(json.dumps(details[0] if details else {},indent=2,sort_keys=True))
    return lb,demo

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--results-dir', default=ROOT/'results'); p.add_argument('--out-dir', default=ROOT/'website'/'data')
    a=p.parse_args(argv); lb,demo=build_data(Path(a.results_dir), Path(a.out_dir)); print(f'wrote {lb} and {demo}')
if __name__ == '__main__': main()
