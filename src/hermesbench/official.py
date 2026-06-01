from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Any

import yaml

from .scoring import aggregate

REQUIRED_MANIFEST_FIELDS = {
    'run_id', 'benchmark_version', 'operator', 'agent', 'model', 'provider', 'agent_version',
    'runner_commit', 'started_at', 'completed_at', 'hardware', 'os', 'timeout_policy',
    'private_pack_id', 'result_json_sha256', 'notes'
}

SENSITIVE_RESULT_KEYS = {'submission_token', 'private_hidden_checks', 'hidden_checks'}


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def load_official_manifest(path: str | Path) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError('official manifest must be a mapping')
    return data


def validate_official_manifest(manifest: dict[str, Any], result_path: str | Path) -> None:
    missing = sorted(REQUIRED_MANIFEST_FIELDS - set(manifest))
    if missing:
        raise ValueError(f"missing official manifest fields: {', '.join(missing)}")
    expected = manifest['result_json_sha256']
    actual = sha256_file(result_path)
    if expected != actual:
        raise ValueError(f'hash mismatch for result JSON: expected {expected}, got {actual}')


def _scrub_result(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _scrub_result(v) for k, v in value.items() if k not in SENSITIVE_RESULT_KEYS}
    if isinstance(value, list):
        return [_scrub_result(v) for v in value]
    return value


def archive_official_run(result_path: str | Path, manifest_path: str | Path, output_dir: str | Path) -> Path:
    result_path = Path(result_path)
    manifest_path = Path(manifest_path)
    output_dir = Path(output_dir)
    manifest = load_official_manifest(manifest_path)
    validate_official_manifest(manifest, result_path)
    output_dir.mkdir(parents=True, exist_ok=True)

    result_data = _scrub_result(json.loads(result_path.read_text()))
    (output_dir / 'result.json').write_text(json.dumps(result_data, indent=2, sort_keys=True) + '\n')
    shutil.copyfile(manifest_path, output_dir / 'manifest.yaml')
    (output_dir / 'score-summary.json').write_text(json.dumps(aggregate(result_path), indent=2, sort_keys=True) + '\n')

    lines = []
    for name in ['result.json', 'manifest.yaml', 'score-summary.json']:
        lines.append(f"{sha256_file(output_dir / name)}  {name}")
    (output_dir / 'SHA256SUMS').write_text('\n'.join(lines) + '\n')
    return output_dir
