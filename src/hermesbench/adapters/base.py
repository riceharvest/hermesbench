from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path

@dataclass
class AgentRun:
    status: str
    transcript: str
    tool_calls: int = 0
    cost_usd: float | None = None
    claimed_done: bool = True
    token_usage: dict[str, int | float] | None = None
    telemetry_source: str | None = None
    tool_events: list[dict] = field(default_factory=list)
    # Fail closed: adapters must explicitly opt in only for controlled,
    # structured tool-event telemetry. Raw model or subprocess stdout is never
    # behavior evidence.
    behavior_evidence_trusted: bool = False
    stalled: bool = False

class AgentAdapter:
    def __init__(self, model: str | None = None, provider: str | None = None, reasoning_effort: str | None = None):
        self.model=model; self.provider=provider; self.reasoning_effort=reasoning_effort
    def run_task(self, task, workdir: Path, hidden_dir: Path | None = None) -> AgentRun: raise NotImplementedError
