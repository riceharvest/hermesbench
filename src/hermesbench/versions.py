from __future__ import annotations

BENCHMARK_VERSIONS = {
    'public-dev-2026-06': {
        'suite': 'public-dev',
        'task_count': 30,
        'status': 'development',
        'notes': 'Fixture-backed public development suite for local runner validation.',
    }
}
DEFAULT_BENCHMARK_VERSION = 'public-dev-2026-06'

def list_versions() -> dict:
    return BENCHMARK_VERSIONS.copy()

def resolve_version(version: str | None) -> dict:
    key = version or DEFAULT_BENCHMARK_VERSION
    if key not in BENCHMARK_VERSIONS:
        raise ValueError(f'unknown benchmark version {key}')
    data = BENCHMARK_VERSIONS[key].copy(); data['version'] = key
    return data
