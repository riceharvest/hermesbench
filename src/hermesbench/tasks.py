from __future__ import annotations
import os, re, yaml
from pathlib import Path
from .schemas import Task, REQUIRED_TASK_FIELDS, GRADING_TYPES

ROOT = Path(__file__).resolve().parents[2]

def parse_task_markdown(path: str | Path) -> Task:
    path=Path(path); text=path.read_text()
    if not text.startswith('---\n'): raise ValueError(f"{path}: missing YAML frontmatter")
    _, yml, body = text.split('---', 2)
    meta = yaml.safe_load(yml) or {}
    missing = REQUIRED_TASK_FIELDS - set(meta)
    if missing: raise ValueError(f"{path}: missing metadata {sorted(missing)}")
    if meta['grading_type'] not in GRADING_TYPES: raise ValueError(f"{path}: bad grading_type")
    sections = dict(re.findall(r'^## ([^\n]+)\n(.*?)(?=^## |\Z)', body, flags=re.M|re.S))
    def lines(name):
        raw=sections.get(name,'')
        return [ln.strip('- ').strip() for ln in raw.splitlines() if ln.strip().startswith('-')]
    checks=[]
    for item in lines('Deterministic checks'):
        if item.startswith('artifact_contains:'):
            _, rest = item.split(':',1); file, needle = rest.strip().split('=>',1)
            checks.append({'type':'artifact_contains','path':file.strip(),'needle':needle.strip()})
        elif item.startswith('artifact_exists:'):
            checks.append({'type':'artifact_exists','path':item.split(':',1)[1].strip()})
        elif item.startswith('json_field:'):
            _, rest=item.split(':',1); file, expr=rest.strip().split('=>',1)
            checks.append({'type':'json_field','path':file.strip(),'expr':expr.strip()})
        elif item.startswith('command_passes:'):
            checks.append({'type':'command_passes','command':item.split(':',1)[1].strip()})
        elif item.startswith('artifact_not_contains:'):
            _, rest = item.split(':',1); file, needle = rest.strip().split('=>',1)
            checks.append({'type':'artifact_not_contains','path':file.strip(),'needle':needle.strip()})
        elif item.startswith('artifact_matches:'):
            _, rest = item.split(':',1); file, pattern = rest.strip().split('=>',1)
            checks.append({'type':'artifact_matches','path':file.strip(),'pattern':pattern.strip()})
        elif item.startswith('artifact_not_matches:'):
            _, rest = item.split(':',1); file, pattern = rest.strip().split('=>',1)
            checks.append({'type':'artifact_not_matches','path':file.strip(),'pattern':pattern.strip()})
        elif item.startswith('glob_exists:'):
            checks.append({'type':'glob_exists','pattern':item.split(':',1)[1].strip()})
        elif item.startswith('command_contains:'):
            _, rest = item.split(':',1); cmd, needle = rest.strip().split('=>',1)
            checks.append({'type':'command_contains','command':cmd.strip(),'needle':needle.strip()})
        elif item.startswith('command_not_contains:'):
            _, rest = item.split(':',1); cmd, needle = rest.strip().split('=>',1)
            checks.append({'type':'command_not_contains','command':cmd.strip(),'needle':needle.strip()})
    return Task(meta, sections.get('Prompt','').strip(), sections.get('Setup','').strip(), lines('Expected artifacts'), sections.get('Scoring rubric','').strip(), checks, lines('Hidden checks'), sections.get('Cleanup','').strip(), str(path))

def _task_base(root: Path = ROOT, task_root: str | Path | None = None) -> Path:
    if task_root:
        return Path(task_root)
    if os.environ.get('HERMESBENCH_PRIVATE_PACK_DIR'):
        return Path(os.environ['HERMESBENCH_PRIVATE_PACK_DIR'])
    return root/'tasks'

def discover_tasks(suite='public-dev', root: Path = ROOT, task_root: str | Path | None = None) -> list[Task]:
    base=_task_base(root, task_root)
    manifest_path=base/'manifest.yaml'
    if not manifest_path.exists():
        raise FileNotFoundError(f'missing manifest {manifest_path}')
    manifest=yaml.safe_load(manifest_path.read_text()) or {}
    tasks=[]
    for entry in manifest.get('tasks', []):
        rel=Path(entry.get('path',''))
        if not rel.parts or rel.parts[0] != suite:
            continue
        path=base/rel
        t=parse_task_markdown(path)
        if t.metadata['id'] != entry.get('id'):
            raise ValueError(f"manifest id mismatch for {path}: {entry.get('id')} != {t.metadata['id']}")
        tasks.append(t)
    return tasks

def validate_tasks(root: Path = ROOT, task_root: str | Path | None = None) -> list[str]:
    errors=[]; ids=set()
    base=_task_base(root, task_root)
    manifest_path=base/'manifest.yaml'
    if not manifest_path.exists(): return [f'missing manifest {manifest_path}']
    manifest = yaml.safe_load(manifest_path.read_text()) or {}
    entries=manifest.get('tasks', [])
    listed={t['id'] for t in entries}
    manifest_paths={Path(t.get('path','')) for t in entries}
    actual_paths={p.relative_to(base) for p in base.glob('*/*.md') if p.name.lower() != 'readme.md' and p.name != 'TASK_TEMPLATE.md'}
    for p in sorted(actual_paths-manifest_paths): errors.append(f'{p} missing from manifest')
    for p in sorted(manifest_paths-actual_paths): errors.append(f'manifest references missing path: {p}')
    tasks=[]
    for suite in sorted({p.parts[0] for p in manifest_paths if p.parts}):
        try:
            tasks.extend(discover_tasks(suite, root, base))
        except Exception as exc:
            errors.append(str(exc))
    for t in tasks:
        tid=t.metadata['id']
        if tid in ids: errors.append(f'duplicate id {tid}')
        ids.add(tid)
        if tid not in listed: errors.append(f'{tid} missing from manifest')
        entry=next((e for e in entries if e.get('id') == tid), {})
        for field in ('category','visibility'):
            if entry.get(field) and entry.get(field) != t.metadata.get(field):
                errors.append(f"{tid} manifest {field} mismatch: {entry.get(field)} != {t.metadata.get(field)}")
        if not t.prompt: errors.append(f'{tid} missing prompt')
        if not t.deterministic_checks: errors.append(f'{tid} has no deterministic checks')
        if t.metadata['visibility'] == 'private' and not t.hidden_checks:
            errors.append(f'{tid} private task has no hidden checks note')
    if listed-ids: errors.append(f'manifest references missing tasks: {sorted(listed-ids)}')
    return errors
