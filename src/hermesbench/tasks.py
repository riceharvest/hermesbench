from __future__ import annotations
import re, yaml
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
    return Task(meta, sections.get('Prompt','').strip(), sections.get('Setup','').strip(), lines('Expected artifacts'), sections.get('Scoring rubric','').strip(), checks, lines('Hidden checks'), sections.get('Cleanup','').strip(), str(path))

def discover_tasks(suite='public-dev', root: Path = ROOT) -> list[Task]:
    task_files=[p for p in (root/'tasks'/suite).glob('*.md') if p.name.lower() != 'readme.md' and p.name != 'TASK_TEMPLATE.md']
    return sorted([parse_task_markdown(p) for p in task_files], key=lambda t:t.metadata['id'])

def validate_tasks(root: Path = ROOT) -> list[str]:
    errors=[]; ids=set()
    manifest = yaml.safe_load((root/'tasks/manifest.yaml').read_text())
    listed={t['id'] for t in manifest['tasks']}
    tasks=[]
    for suite_dir in (root/'tasks').iterdir():
        if suite_dir.is_dir():
            tasks.extend(discover_tasks(suite_dir.name, root))
    for t in tasks:
        tid=t.metadata['id']
        if tid in ids: errors.append(f'duplicate id {tid}')
        ids.add(tid)
        if tid not in listed: errors.append(f'{tid} missing from manifest')
        if not t.prompt: errors.append(f'{tid} missing prompt')
        if not t.deterministic_checks: errors.append(f'{tid} has no deterministic checks')
        if t.metadata['visibility'] == 'private' and not t.hidden_checks:
            errors.append(f'{tid} private task has no hidden checks note')
    if listed-ids: errors.append(f'manifest references missing tasks: {sorted(listed-ids)}')
    return errors
