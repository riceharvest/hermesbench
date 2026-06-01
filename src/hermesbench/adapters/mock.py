from pathlib import Path
from .base import AgentAdapter, AgentRun

class MockAdapter(AgentAdapter):
    def run_task(self, task, workdir: Path) -> AgentRun:
        for artifact in task.expected_artifacts:
            p=workdir/artifact; p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(f"task_id: {task.metadata['id']}\ncategory: {task.metadata['category']}\nverified: true\nsummary: mock completion for {task.metadata['title']}\n")
        # ensure deterministic needles exist
        for c in task.deterministic_checks:
            if c['type']=='artifact_contains':
                p=workdir/c['path']; p.parent.mkdir(parents=True, exist_ok=True)
                txt=p.read_text() if p.exists() else ''
                if c['needle'] not in txt: p.write_text(txt + '\n' + c['needle'] + '\n')
        return AgentRun(status='completed', transcript='mock adapter created requested artifacts and verification evidence', tool_calls=2)
