from dataclasses import dataclass
from pathlib import Path

@dataclass
class AgentRun:
    status: str
    transcript: str
    tool_calls: int = 0
    cost_usd: float | None = None
    claimed_done: bool = True

class AgentAdapter:
    def __init__(self, model: str | None = None, provider: str | None = None, reasoning_effort: str | None = None):
        self.model=model; self.provider=provider; self.reasoning_effort=reasoning_effort
    def run_task(self, task, workdir: Path) -> AgentRun: raise NotImplementedError
