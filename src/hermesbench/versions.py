from __future__ import annotations

from .tasks import discover_tasks


def _task_count(suite: str) -> int:
    """Return the manifest-backed count for a published suite."""
    return len(discover_tasks(suite))

BENCHMARK_VERSIONS = {
    'hermes-core-v0.1': {
        'suite': 'hermes-core',
        'task_count': _task_count('hermes-core'),
        'status': 'development',
        'notes': 'Hermes Agent tools and features shipped in the base installation.',
    },
    'hermes-extended-v0.1': {
        'suite': 'hermes-extended',
        'task_count': _task_count('hermes-extended'),
        'status': 'development',
        'notes': 'Installable and configurable Hermes ecosystem tools and integrations.',
    },
    'hermes-core-v0.2-private': {
        'suite': 'hermes-core-private',
        'task_count': 13,
        'status': 'private-evaluation',
        'notes': 'Fresh private equivalents of the base Hermes tool-capability probes.',
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
