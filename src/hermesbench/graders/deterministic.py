from __future__ import annotations
import json, re, subprocess
from pathlib import Path
from typing import Any


def _coerce_expected(value: str):
    v=value.strip()
    if v.lower() == 'true': return True
    if v.lower() == 'false': return False
    if v.lower() in {'null','none'}: return None
    try: return int(v)
    except ValueError:
        try: return float(v)
        except ValueError: return v.strip('"\'')


def _json_path(data: Any, dotted: str) -> Any:
    cur=data
    for part in dotted.strip().split('.'):
        if not part:
            continue
        m=re.fullmatch(r'([^\[]+)(?:\[(\d+)\])?', part)
        key=part; idx=None
        if m:
            key=m.group(1); idx=m.group(2)
        if isinstance(cur, dict) and key in cur:
            cur=cur[key]
        else:
            return '<missing>'
        if idx is not None:
            if isinstance(cur, list) and int(idx) < len(cur): cur=cur[int(idx)]
            else: return '<missing>'
    return cur


def _compare(actual: Any, expr: str) -> bool:
    for op in ('~=', '>=', '<=', '!=', '>', '<', '='):
        if op in expr:
            key, val = expr.split(op, 1)
            expected=_coerce_expected(val)
            break
    else:
        return bool(_json_path(actual, expr))
    got=_json_path(actual, key.strip())
    if got == '<missing>': return False
    if op == '~=':
        target, _, tol = str(expected).partition('±')
        if not tol and '+/-' in str(expected): target, tol = str(expected).split('+/-',1)
        try: return abs(float(got)-float(target)) <= float(tol or 1e-9)
        except Exception: return False
    if op in ('>','<','>=','<='):
        try:
            g=float(got); e=float(expected)
            return {'>': g>e, '<': g<e, '>=': g>=e, '<=': g<=e}[op]
        except Exception: return False
    return (got != expected) if op == '!=' else (got == expected)


def _run_command(command: str, workdir: Path, timeout: float) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(command, cwd=workdir, shell=True, timeout=timeout, capture_output=True, text=True)
    except Exception:
        return None


def run_checks(workdir: Path, checks: list[dict]) -> tuple[float, list[str]]:
    evidence=[]; passed=0
    for c in checks:
        timeout=float(c.get('timeout_seconds', c.get('timeout', 10)))
        p=workdir/c.get('path','')
        ok=False; detail=''
        typ=c['type']
        if typ=='artifact_exists': ok=p.exists()
        elif typ=='glob_exists': ok=any(workdir.glob(c.get('pattern','')))
        elif typ=='artifact_contains': ok=p.exists() and c.get('needle','') in p.read_text(errors='ignore')
        elif typ=='artifact_not_contains': ok=p.exists() and c.get('needle','') not in p.read_text(errors='ignore')
        elif typ=='artifact_matches': ok=p.exists() and re.search(c.get('pattern',''), p.read_text(errors='ignore'), re.S) is not None
        elif typ=='artifact_not_matches': ok=p.exists() and re.search(c.get('pattern',''), p.read_text(errors='ignore'), re.S) is None
        elif typ=='json_field':
            actual='<missing>'
            try:
                data=json.loads(p.read_text()); actual=data
                ok=_compare(data, c['expr'])
                key=re.split(r'~=|>=|<=|!=|=|>|<', c['expr'], maxsplit=1)[0].strip()
                actual=_json_path(data, key)
            except Exception as exc:
                actual=f'<error: {exc.__class__.__name__}>'
            detail='' if ok else f' (actual={actual})'
        elif typ in {'command_passes','command_contains','command_not_contains'}:
            cp=_run_command(c['command'], workdir, timeout)
            out='' if cp is None else (cp.stdout or '') + (cp.stderr or '')
            if typ=='command_passes': ok=cp is not None and cp.returncode == 0
            elif typ=='command_contains': ok=cp is not None and c.get('needle','') in out
            elif typ=='command_not_contains': ok=cp is not None and c.get('needle','') not in out
            detail=f' (rc={getattr(cp, "returncode", None)})' if not ok else ''
        target=c.get('path') or c.get('pattern') or c.get('command')
        if typ == 'json_field' and c.get('expr'):
            target=f"{target} {c['expr']}"
        evidence.append(f"{typ} {target}: {'PASS' if ok else 'FAIL'}{detail}")
        passed += int(ok)
    return (passed/len(checks) if checks else 0.0), evidence
