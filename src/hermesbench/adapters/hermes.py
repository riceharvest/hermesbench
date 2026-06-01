import subprocess
from pathlib import Path
from .base import AgentAdapter, AgentRun
class HermesCLIAdapter(AgentAdapter):
    def run_task(self, task, workdir: Path) -> AgentRun:
        prompt=f"HermesBench task {task.metadata['id']}\n\n{task.prompt}\n\nWorkdir: {workdir}. Produce expected artifacts: {', '.join(task.expected_artifacts)}. Verify before final."
        cmd=['hermes','chat','-q',prompt,'-Q','--toolsets','terminal,file,web,browser']
        if self.model: cmd += ['--model', self.model]
        p=subprocess.run(cmd, cwd=workdir, text=True, capture_output=True, timeout=int(task.metadata['timeout_seconds']))
        return AgentRun('completed' if p.returncode==0 else 'failed', p.stdout+p.stderr, 0)
