from __future__ import annotations
import argparse, json, math, statistics
from pathlib import Path
from hermesbench.scoring import aggregate

ROOT = Path(__file__).resolve().parents[1]


def _model_key(entry: dict) -> tuple[str, str, str, str, bool]:
    return (
        entry.get("agent") or "",
        entry.get("provider") or "",
        entry.get("model") or "",
        entry.get("reasoning_effort") or "",
        bool(entry.get("official")),
    )


def _summarize_group(rows: list[dict]) -> dict:
    best = max(rows, key=lambda e: (e.get("score_percentage", e.get("overall_score", 0)), e.get("pass_at_1", 0)))
    scores = [float(e.get("score_percentage", e.get("overall_score", 0)) or 0) for e in rows]
    avg = statistics.mean(scores) if scores else 0
    std = statistics.stdev(scores) if len(scores) > 1 else 0.0
    ci = 1.96 * std / math.sqrt(len(scores)) if len(scores) > 1 else 0.0
    total_costs = [e.get("total_cost_usd", e.get("cost_usd")) for e in rows if e.get("total_cost_usd", e.get("cost_usd")) is not None]
    times = [e.get("total_execution_time_seconds") for e in rows if e.get("total_execution_time_seconds") is not None]
    tokens = [e.get("total_tokens") for e in rows if e.get("total_tokens") is not None]
    tools = [e.get("tool_call_count") for e in rows if e.get("tool_call_count") is not None]
    agent, provider, model, reasoning, official = _model_key(best)
    return {
        "agent": agent,
        "provider": provider or None,
        "model": model or None,
        "reasoning_effort": reasoning or None,
        "official": official,
        "classification": "official" if official else "unofficial",
        "submission_count": len(rows),
        "best_submission_id": best.get("run_id"),
        "best_score_percentage": max(scores) if scores else 0,
        "average_score_percentage": avg,
        "score_stddev": std,
        "score_ci95_low": max(0, avg - ci),
        "score_ci95_high": min(1, avg + ci),
        "average_pass_at_1": statistics.mean([e.get("pass_at_1", 0) for e in rows]),
        "average_false_done_rate": statistics.mean([e.get("false_done_rate", 0) for e in rows]),
        "average_timeout_rate": statistics.mean([e.get("timeout_rate", 0) for e in rows]),
        "average_cost_usd": statistics.mean(total_costs) if total_costs else None,
        "average_execution_time_seconds": statistics.mean(times) if times else None,
        "average_total_tokens": statistics.mean(tokens) if tokens else None,
        "average_tool_call_count": statistics.mean(tools) if tools else None,
    }


def build_data(results_dir: Path = ROOT / "results", out_dir: Path = ROOT / "website" / "data") -> tuple[Path, Path]:
    entries=[]; details=[]
    for result_path in sorted(results_dir.glob("**/hermesbench-*.json")):
        data=json.loads(result_path.read_text())
        score=aggregate(result_path)
        official=bool(data.get("metadata", {}).get("official"))
        try:
            source=str(result_path.relative_to(ROOT))
        except ValueError:
            source=str(result_path)
        entry={**score,"official":official,"classification":"official" if official else "unofficial","source":source}
        entries.append(entry)
        details.append({**score,"official":official,"classification":entry["classification"],"tasks":data.get("results",[])[:8],"source":entry["source"]})
    entries.sort(key=lambda e: (not e["official"], -e["overall_score"], e["run_id"]))
    for i,e in enumerate([e for e in entries if e["official"]],1): e["rank"]=i
    for i,e in enumerate([e for e in entries if not e["official"]],1): e["rank"]=i
    groups: dict[tuple[str, str, str, str, bool], list[dict]] = {}
    for entry in entries:
        groups.setdefault(_model_key(entry), []).append(entry)
    summaries=sorted((_summarize_group(rows) for rows in groups.values()), key=lambda e: (not e["official"], -e["average_score_percentage"], -(e["submission_count"])))
    payload={"schema_version":"hermesbench.website.leaderboard.v2","generated_from":"committed results/ files","metric_notes":"Public-dev rows are single-run samples unless grouped by repeated runs; official rankings require maintainer private/fresh packs.","official":[e for e in entries if e["official"]],"unofficial":[e for e in entries if not e["official"]],"model_summaries":summaries,"entries":entries}
    out_dir.mkdir(parents=True, exist_ok=True)
    lb=out_dir/"leaderboard.json"; lb.write_text(json.dumps(payload,indent=2,sort_keys=True))
    demo=out_dir/"latest-result.json"; demo.write_text(json.dumps(details[0] if details else {},indent=2,sort_keys=True))
    return lb,demo


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--results-dir", default=ROOT/"results"); p.add_argument("--out-dir", default=ROOT/"website"/"data")
    a=p.parse_args(argv); lb,demo=build_data(Path(a.results_dir), Path(a.out_dir)); print(f"wrote {lb} and {demo}")
if __name__ == "__main__": main()
