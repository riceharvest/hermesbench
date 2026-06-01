from .base import AgentAdapter, AgentRun
from .mock import MockAdapter
from .shell import ShellAdapter
from .hermes import HermesCLIAdapter

def get_adapter(name: str, model: str | None = None, command: str | None = None, provider: str | None = None, reasoning_effort: str | None = None):
    if name == 'mock': return MockAdapter(model=model, provider=provider, reasoning_effort=reasoning_effort)
    if name == 'shell': return ShellAdapter(command=command or 'true', model=model, provider=provider, reasoning_effort=reasoning_effort)
    if name == 'hermes': return HermesCLIAdapter(model=model, provider=provider, reasoning_effort=reasoning_effort)
    raise ValueError(f'unknown adapter {name}')
