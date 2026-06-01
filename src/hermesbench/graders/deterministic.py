from __future__ import annotations
import json, subprocess
from pathlib import Path

def _coerce_expected(value: str):
    v=value.strip()
    if v.lower() == 'true': return True
    if v.lower() == 'false': return False
    if v.lower() in {'null','none'}: return None
    try: return int(v)
    except ValueError:
        try: return float(v)
        except ValueError: return v

def run_checks(workdir: Path, checks: list[dict]) -> tuple[float, list[str]]:
    evidence=[]; passed=0
    for c in checks:
        p=workdir/c.get('path','')
        ok=False
        if c['type']=='artifact_exists': ok=p.exists()
        elif c['type']=='artifact_contains': ok=p.exists() and c.get('needle','') in p.read_text(errors='ignore')
        elif c['type']=='json_field':
            actual = '<missing>'
            try:
                data=json.loads(p.read_text()); key,val=c['expr'].split('=',1)
                actual=data.get(key.strip(), '<missing>')
                ok=actual == _coerce_expected(val)
            except Exception as exc:
                actual=f'<error: {exc.__class__.__name__}>'
            suffix = '' if ok else f" (actual={actual})"
            evidence.append(f"{c['type']} {c.get('path')} {c.get('expr')}: {'PASS' if ok else 'FAIL'}{suffix}")
            passed += int(ok)
            continue
        elif c['type']=='command_passes':
            try:
                ok=subprocess.run(c['command'], cwd=workdir, shell=True, timeout=10, capture_output=True, text=True).returncode == 0
            except Exception: ok=False
        evidence.append(f"{c['type']} {c.get('path') or c.get('command')}: {'PASS' if ok else 'FAIL'}")
        passed += int(ok)
    return (passed/len(checks) if checks else 0.0), evidence
