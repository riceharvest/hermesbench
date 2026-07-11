from __future__ import annotations

BENCHMARK_VERSIONS = {
    'hermes-core-v0.1': {
        'suite': 'hermes-core',
        'task_count': 13,
        'status': 'development',
        'notes': 'Hermes Agent tools and features shipped in the base installation.',
    },
    'hermes-extended-v0.1': {
        'suite': 'hermes-extended',
        'task_count': 25,
        'status': 'development',
        'notes': 'Installable and configurable Hermes ecosystem tools and integrations.',
    },
}
DEFAULT_BENCHMARK_VERSION = 'hermes-core-v0.1'

def list_versions() -> dict:
    return BENCHMARK_VERSIONS.copy()

def resolve_version(version: str | None) -> dict:
    key = version or DEFAULT_BENCHMARK_VERSION
    if key not in BENCHMARK_VERSIONS:
        raise ValueError(f'unknown benchmark version {key}')
    data = BENCHMARK_VERSIONS[key].copy(); data['version'] = key
    return data
