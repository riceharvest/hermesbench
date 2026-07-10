from __future__ import annotations

BENCHMARK_VERSIONS = {
    'core-cli-v0.1': {
        'suite': 'core-cli',
        'task_count': 3,
        'status': 'development',
        'notes': 'Hermes CLI-supported core tool suite.',
    },
    'natural-tools-dev-v0.1': {
        'suite': 'natural-tools-dev',
        'task_count': 38,
        'status': 'development',
        'notes': 'Minimum-capable-model probe for Hermes Agent tool coverage.',
    }
}
DEFAULT_BENCHMARK_VERSION = 'core-cli-v0.1'

def list_versions() -> dict:
    return BENCHMARK_VERSIONS.copy()

def resolve_version(version: str | None) -> dict:
    key = version or DEFAULT_BENCHMARK_VERSION
    if key not in BENCHMARK_VERSIONS:
        raise ValueError(f'unknown benchmark version {key}')
    data = BENCHMARK_VERSIONS[key].copy(); data['version'] = key
    return data
