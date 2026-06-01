from __future__ import annotations
import json
from pathlib import Path

def run_checks(workdir: Path, checks: list[dict]) -> tuple[float, list[str]]:
    evidence=[]; passed=0
    for c in checks:
        p=workdir/c.get('path','')
        ok=False
        if c['type']=='artifact_exists': ok=p.exists()
        elif c['type']=='artifact_contains': ok=p.exists() and c.get('needle','') in p.read_text(errors='ignore')
        elif c['type']=='json_field':
            try:
                data=json.loads(p.read_text()); key,val=c['expr'].split('=',1); ok=str(data.get(key.strip()))==val.strip()
            except Exception: ok=False
        evidence.append(f"{c['type']} {c.get('path')}: {'PASS' if ok else 'FAIL'}")
        passed += int(ok)
    return (passed/len(checks) if checks else 0.0), evidence
