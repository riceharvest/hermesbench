from __future__ import annotations
import os, re, yaml
from pathlib import Path
from .schemas import Task, REQUIRED_TASK_FIELDS, GRADING_TYPES, QUALITY_TIERS, NATURAL_TOOL_CLASSES, Any

ROOT = Path(__file__).resolve().parents[2]
QUALITY_TEMPLATE_SECTIONS = ("Failure mode tested", "Why hard for agents", "Overfitting risk")
COMMAND_CHECK_TYPES = {"command_passes", "command_contains", "command_not_contains"}
SEMANTIC_CHECK_TYPES = {"json_field", "artifact_matches", "artifact_not_matches", "artifact_not_contains", *COMMAND_CHECK_TYPES}

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

def _validate_tool_use_requirements(meta: dict[str, Any], tid: str) -> list[str]:
    findings = []
    reqs = meta.get('tool_use_requirements', [])
    if reqs is not None and not isinstance(reqs, list):
        findings.append(f'ERROR {tid}: tool_use_requirements must be a list or omitted')
        return findings
    invalid = set(reqs or []) - NATURAL_TOOL_CLASSES
    if invalid:
        findings.append(f'ERROR {tid}: tool_use_requirements contains unknown tool classes: {sorted(invalid)}')
    return findings

def task_quality_findings(task: Task, root: Path = ROOT) -> list[str]:
    """Return quality lint findings as WARNING/ERROR strings for one task.

    Findings are deliberately conservative so older task packs keep parsing, while
    `validate-tasks` still surfaces shallow or overfit-prone tasks to maintainers.
    """
    tid=task.metadata.get('id','<unknown>')
    findings=[]
    findings.extend(_validate_tool_use_requirements(task.metadata, tid))
    checks=task.deterministic_checks or []
    if len(checks) <= 3:
        findings.append(f'WARNING {tid}: quality lint: has {len(checks)} deterministic checks; use at least 4 independent checks')
    artifacts=[str(a).lower() for a in task.expected_artifacts]
    if artifacts and all(a.endswith(('marker.txt','completion.txt','done.txt','success.txt')) for a in artifacts):
        findings.append(f'WARNING {tid}: quality lint: expected artifacts look marker-only')
    if checks and all(c.get('type') == 'artifact_exists' or (c.get('type') == 'artifact_contains' and str(c.get('needle','')).lower() in {'done','ok','success','complete','completed'}) for c in checks):
        findings.append(f'ERROR {tid}: quality lint: deterministic checks are marker-only and do not validate task substance')
    if checks and not any(c.get('type') in COMMAND_CHECK_TYPES for c in checks):
        findings.append(f'WARNING {tid}: quality lint: no command-based validation check')
    if checks and not any(c.get('type') in SEMANTIC_CHECK_TYPES for c in checks):
        findings.append(f'ERROR {tid}: quality lint: no semantic validation beyond file existence/markers')
    fixture_dir=root/'fixtures'/tid
    fixture_files=[p for p in fixture_dir.rglob('*') if p.is_file()] if fixture_dir.exists() else []
    fixture_bytes=sum(p.stat().st_size for p in fixture_files) if fixture_files else 0
    if task.metadata.get('no_fixture_required') is not True and fixture_bytes < 128:
        findings.append(f'WARNING {tid}: quality lint: tiny or missing fixture set ({fixture_bytes} bytes); set no_fixture_required: true when intentional')
    sections = getattr(task, 'sections', None)
    # Task dataclass stays backward-compatible; re-read sections from source for strict template lint.
    source = Path(task.path)
    if source.exists():
        body = source.read_text().split('---',2)[2] if source.read_text().startswith('---\n') else source.read_text()
        sections = dict(re.findall(r'^## ([^\n]+)\n(.*?)(?=^## |\Z)', body, flags=re.M|re.S))
    for section in QUALITY_TEMPLATE_SECTIONS:
        if not (sections or {}).get(section,'').strip():
            findings.append(f'WARNING {tid}: quality lint: missing template section "{section}"')
    tier=task.metadata.get('quality_tier')
    if tier and tier not in QUALITY_TIERS:
        findings.append(f'ERROR {tid}: quality lint: unknown quality_tier {tier!r}')
    return findings

def task_quality_tier(task: Task, root: Path = ROOT) -> str:
    explicit=task.metadata.get('quality_tier')
    if explicit in QUALITY_TIERS:
        return explicit
    findings=task_quality_findings(task, root)
    if any(f.startswith('ERROR') for f in findings):
        return 'needs-review'
    warnings=sum(1 for f in findings if f.startswith('WARNING'))
    if warnings == 0:
        return 'gold'
    if warnings <= 2:
        return 'silver'
    return 'bronze'

def _task_base(root: Path = ROOT, task_root: str | Path | None = None) -> Path:
    if task_root:
        return Path(task_root)
    if os.environ.get('HERMESBENCH_PRIVATE_PACK_DIR'):
        return Path(os.environ['HERMESBENCH_PRIVATE_PACK_DIR'])
    return root/'tasks'

def _suite_entries(manifest: dict, suite: str) -> list[dict]:
    """Return task entries for a named suite, supporting legacy list and multi-suite `suites` dict formats.

    For legacy manifests, the top-level `suite` field is also honored when the
    requested suite matches (or when no suite name was provided and the fallback
    default `hermes-core` is requested).
    """
    suites_meta = manifest.get('suites', {})
    raw_tasks = manifest.get('tasks', [])
    if isinstance(suites_meta, dict) and suite in suites_meta:
        return suites_meta[suite].get('tasks', [])
    if isinstance(raw_tasks, dict):
        return raw_tasks.get(suite, {}).get('tasks', [])
    # Legacy single-suite manifest with a top-level `suite` field.
    if isinstance(raw_tasks, list) and manifest.get('suite') == suite:
        return raw_tasks
    return []


def discover_tasks(suite='hermes-core', root: Path = ROOT, task_root: str | Path | None = None) -> list[Task]:
    base=_task_base(root, task_root)
    manifest_path=base/'manifest.yaml'
    if not manifest_path.exists():
        raise FileNotFoundError(f'missing manifest {manifest_path}')
    manifest=yaml.safe_load(manifest_path.read_text()) or {}
    entries = _suite_entries(manifest, suite)
    tasks=[]
    for entry in entries:
        rel=Path(entry.get('path',''))
        if not rel.parts:
            continue
        path=base/rel
        t=parse_task_markdown(path)
        if t.metadata['id'] != entry.get('id'):
            raise ValueError(f"manifest id mismatch for {path}: {entry.get('id')} != {t.metadata['id']}")
        tasks.append(t)
    return tasks


def _safe_relative_path(value: object) -> bool:
    """Return whether a declared path is confined to the task sandbox."""
    path = Path(str(value))
    return bool(str(value)) and not path.is_absolute() and ".." not in path.parts


def _fixture_contract_findings(task: Task, fixtures_root: Path) -> list[str]:
    """Validate explicitly declared fixture inputs and artifact destinations."""
    tid = task.metadata['id']
    findings: list[str] = []
    declared: list[object] = []
    for key in ('fixtures', 'fixture', 'inputs', 'input_files'):
        value = task.metadata.get(key)
        if value is not None:
            declared.extend(value if isinstance(value, list) else [value])
    for value in declared:
        if not _safe_relative_path(value) or not (fixtures_root / tid / str(value)).is_file():
            findings.append(f'ERROR {tid}: declared fixture missing or unsafe: {value}')
    artifact_paths = list(task.expected_artifacts)
    artifact_paths.extend(check['path'] for check in task.deterministic_checks if check.get('path'))
    for value in artifact_paths:
        if not _safe_relative_path(value):
            findings.append(f'ERROR {tid}: unsafe artifact path: {value}')
    return findings


def _manifest_entries(manifest: dict) -> list[dict]:
    """Return flat task entries across all suites for validation purposes."""
    entries: list[dict] = []
    for suite_name in _manifest_suite_names(manifest):
        entries.extend(_suite_entries(manifest, suite_name))
    return entries


def _manifest_suite_names(manifest: dict) -> list[str]:
    """Return all suite names declared in the manifest."""
    suites_meta = manifest.get('suites', {})
    raw_tasks = manifest.get('tasks', [])
    if isinstance(suites_meta, dict) and suites_meta:
        return sorted(suites_meta.keys())
    if isinstance(raw_tasks, dict) and raw_tasks:
        return sorted(raw_tasks.keys())
    # Legacy single-suite manifest: honor top-level `suite` if present, otherwise default.
    if manifest.get('suite'):
        return [str(manifest['suite'])]
    return ['default']


def validate_tasks(root: Path = ROOT, task_root: str | Path | None = None, include_quality: bool = False, quality_only: bool = False) -> list[str]:
    errors=[]; ids: dict[str, str] = {}
    base=_task_base(root, task_root)
    # Quality-only calls should not be affected by manifest structural checks; the
    # caller may just want the lint findings for a single synthetic task. We use
    # `discover_tasks('default', ...)` as a fallback for legacy single-suite manifests.
    manifest_path=base/'manifest.yaml'
    if not manifest_path.exists(): return [f'missing manifest {manifest_path}']
    manifest = yaml.safe_load(manifest_path.read_text()) or {}
    entries=_manifest_entries(manifest)
    listed={t['id'] for t in entries}
    manifest_paths={Path(t.get('path','')) for t in entries}
    actual_paths={p.relative_to(base) for p in base.glob('*/*.md') if p.name.lower() != 'readme.md' and p.name != 'TASK_TEMPLATE.md'}
    if not quality_only:
        for p in sorted(actual_paths - manifest_paths):
            # Only complain if a file is under a suite that has *some* entries in the manifest.
            suite = p.parts[0] if p.parts else ''
            if any(Path(e.get('path', '')).parts[0] == suite for e in entries):
                errors.append(f'{p} missing from manifest')
        for p in sorted(manifest_paths - actual_paths):
            errors.append(f'manifest references missing path: {p}')
    tasks=[]
    suites=_manifest_suite_names(manifest)
    for suite in suites:
        try:
            tasks.extend(discover_tasks(suite, root, base))
        except Exception as exc:
            errors.append(str(exc))
    for t in tasks:
        tid=t.metadata['id']
        # In multi-suite manifests, a task may legitimately appear under more than one suite.
        # Only flag as duplicates when the same task id is repeated within the same
        # manifest path.
        if not quality_only and tid in ids:
            seen_path = ids[tid]
            if seen_path != t.path:
                errors.append(f'duplicate id {tid}')
        ids[tid] = t.path
        if not quality_only and tid not in listed: errors.append(f'{tid} missing from manifest')
        entry=next((e for e in entries if e.get('id') == tid), {})
        if not quality_only:
            for field in ('category','visibility'):
                if entry.get(field) and entry.get(field) != t.metadata.get(field):
                    errors.append(f"{tid} manifest {field} mismatch: {entry.get(field)} != {t.metadata.get(field)}")
            if not t.prompt: errors.append(f'{tid} missing prompt')
            if not t.deterministic_checks: errors.append(f'{tid} has no deterministic checks')
            if t.metadata['visibility'] == 'private' and not t.hidden_checks:
                errors.append(f'{tid} private task has no hidden checks note')
            errors.extend(_fixture_contract_findings(t, base.parent / 'fixtures'))
        if include_quality or quality_only:
            errors.extend(task_quality_findings(t, base.parent if base.name == 'tasks' else root))
    if not quality_only and listed - set(ids):
        # In multi-suite manifests, a task may legitimately appear under more than one suite.
        # Only flag tasks that are listed but were never discovered.
        missing = listed - set(ids)
        if missing:
            errors.append(f'manifest references missing tasks: {sorted(missing)}')
    return errors
