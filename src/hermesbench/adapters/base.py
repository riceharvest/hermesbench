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
    def __init__(self, model: str | None = None): self.model=model
    def run_task(self, task, workdir: Path) -> AgentRun: raise NotImplementedError
