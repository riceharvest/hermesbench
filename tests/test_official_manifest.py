import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from hermesbench.official import archive_official_run, load_official_manifest, validate_official_manifest
from hermesbench.runner import run_benchmark


def _result(tmp_path):
    return Path(run_benchmark(agent='mock', suite='public-dev', task_id='hb-dev-001-sanity-basic-tool-use', output_dir=tmp_path))


def _manifest(result_path, **overrides):
    import hashlib
    data = {
        'run_id': 'official-20260601-mock',
        'benchmark_version': 'hermesbench-v0.1',
        'operator': 'maintainer-name',
        'agent': 'mock',
        'model': 'mock',
        'provider': 'local',
        'agent_version': '0.1.0',
        'runner_commit': 'abc123',
        'started_at': '2026-06-01T00:00:00Z',
        'completed_at': '2026-06-01T00:01:00Z',
        'hardware': 'ci',
        'os': 'linux',
        'timeout_policy': 'task default',
        'private_pack_id': 'maintainer-pack-v1',
        'result_json_sha256': hashlib.sha256(result_path.read_bytes()).hexdigest(),
        'notes': 'test manifest',
    }
    data.update(overrides)
    return data


def test_valid_official_manifest_loads(tmp_path):
    result = _result(tmp_path)
    manifest_path = tmp_path / 'manifest.yaml'
    manifest_path.write_text(yaml.safe_dump(_manifest(result)))
    manifest = load_official_manifest(manifest_path)
    validate_official_manifest(manifest, result)
    assert manifest['run_id'].startswith('official-')


def test_missing_required_manifest_field_fails(tmp_path):
    result = _result(tmp_path)
    manifest = _manifest(result)
    manifest.pop('operator')
    with pytest.raises(ValueError, match='operator'):
        validate_official_manifest(manifest, result)


def test_result_hash_mismatch_fails(tmp_path):
    result = _result(tmp_path)
    manifest = _manifest(result, result_json_sha256='bad')
    with pytest.raises(ValueError, match='hash mismatch'):
        validate_official_manifest(manifest, result)


def test_archive_official_command_creates_public_safe_archive(tmp_path):
    result = _result(tmp_path)
    payload = json.loads(result.read_text())
    payload['submission_token'] = 'secret'
    payload['results'][0]['logs'] = {'hidden_checks': ['do not publish'], 'stdout': 'ok'}
    result.write_text(json.dumps(payload))
    manifest_path = tmp_path / 'manifest.yaml'
    manifest_path.write_text(yaml.safe_dump(_manifest(result)))
    archive = archive_official_run(result, manifest_path, tmp_path / 'archive')
    assert (archive / 'result.json').exists()
    assert (archive / 'manifest.yaml').exists()
    assert (archive / 'score-summary.json').exists()
    assert (archive / 'SHA256SUMS').read_text().strip()
    public_result = json.loads((archive / 'result.json').read_text())
    assert 'submission_token' not in public_result
    assert 'hidden_checks' not in public_result['results'][0].get('logs', {})


def test_archive_official_cli(tmp_path):
    result = _result(tmp_path)
    manifest_path = tmp_path / 'manifest.yaml'
    manifest_path.write_text(yaml.safe_dump(_manifest(result)))
    out = tmp_path / 'cli-archive'
    completed = subprocess.run([
        sys.executable, '-m', 'hermesbench.cli', 'archive-official', '--result', str(result), '--manifest', str(manifest_path), '--output', str(out)
    ], check=True, text=True, capture_output=True)
    assert str(out) in completed.stdout
    assert (out / 'score-summary.json').exists()
