from .base import AgentAdapter, AgentRun
from .mock import MockAdapter
from .shell import ShellAdapter
from .hermes import HermesCLIAdapter

def get_adapter(name: str, model: str | None = None, command: str | None = None):
    if name == 'mock': return MockAdapter(model=model)
    if name == 'shell': return ShellAdapter(command=command or 'true', model=model)
    if name == 'hermes': return HermesCLIAdapter(model=model)
    raise ValueError(f'unknown adapter {name}')
