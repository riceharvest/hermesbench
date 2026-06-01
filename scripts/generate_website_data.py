from __future__ import annotations
import argparse, json
from pathlib import Path
from hermesbench.scoring import aggregate

ROOT = Path(__file__).resolve().parents[1]


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
    payload={"schema_version":"hermesbench.website.leaderboard.v1","generated_from":"committed results/ files","official":[e for e in entries if e["official"]],"unofficial":[e for e in entries if not e["official"]],"entries":entries}
    out_dir.mkdir(parents=True, exist_ok=True)
    lb=out_dir/"leaderboard.json"; lb.write_text(json.dumps(payload,indent=2,sort_keys=True))
    demo=out_dir/"latest-result.json"; demo.write_text(json.dumps(details[0] if details else {},indent=2,sort_keys=True))
    return lb,demo


def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--results-dir", default=ROOT/"results"); p.add_argument("--out-dir", default=ROOT/"website"/"data")
    a=p.parse_args(argv); lb,demo=build_data(Path(a.results_dir), Path(a.out_dir)); print(f"wrote {lb} and {demo}")
if __name__ == "__main__": main()
