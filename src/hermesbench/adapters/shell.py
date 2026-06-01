import subprocess, shlex
from pathlib import Path
from .base import AgentAdapter, AgentRun
class ShellAdapter(AgentAdapter):
    def __init__(self, command: str, model: str | None=None): super().__init__(model); self.command=command
    def run_task(self, task, workdir: Path) -> AgentRun:
        p=subprocess.run(self.command, shell=True, cwd=workdir, text=True, capture_output=True, timeout=int(task.metadata['timeout_seconds']))
        return AgentRun('completed' if p.returncode==0 else 'failed', p.stdout+p.stderr, 0)
