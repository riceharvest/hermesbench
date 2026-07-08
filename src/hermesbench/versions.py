from __future__ import annotations

BENCHMARK_VERSIONS = {
    'natural-tools-dev-v0.1': {
        'suite': 'natural-tools-dev',
        'task_count': 5,
        'status': 'development',
        'notes': 'Minimum-capable-model probe for Hermes Agent tool coverage.',
    }
}
DEFAULT_BENCHMARK_VERSION = 'natural-tools-dev-v0.1'

def list_versions() -> dict:
    return BENCHMARK_VERSIONS.copy()

def resolve_version(version: str | None) -> dict:
    key = version or DEFAULT_BENCHMARK_VERSION
    if key not in BENCHMARK_VERSIONS:
        raise ValueError(f'unknown benchmark version {key}')
    data = BENCHMARK_VERSIONS[key].copy(); data['version'] = key
    return data
