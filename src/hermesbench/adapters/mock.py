from pathlib import Path
import json
from .base import AgentAdapter, AgentRun

def _coerce(value: str):
    v=value.strip()
    if v.lower() == 'true': return True
    if v.lower() == 'false': return False
    if v.lower() in {'null','none'}: return None
    try: return int(v)
    except ValueError:
        try: return float(v)
        except ValueError: return v

class MockAdapter(AgentAdapter):
    def run_task(self, task, workdir: Path) -> AgentRun:
        for artifact in task.expected_artifacts:
            p=workdir/artifact; p.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix == '.json':
                p.write_text(json.dumps({'task_id': task.metadata['id'], 'category': task.metadata['category'], 'verified': True}, indent=2, sort_keys=True))
            else:
                p.write_text(f"task_id: {task.metadata['id']}\ncategory: {task.metadata['category']}\nverified: true\nsummary: mock completion for {task.metadata['title']}\n")
        # ensure deterministic needles and fields exist
        for c in task.deterministic_checks:
            if c['type']=='artifact_contains':
                p=workdir/c['path']; p.parent.mkdir(parents=True, exist_ok=True)
                txt=p.read_text() if p.exists() else ''
                if c['needle'] not in txt: p.write_text(txt + '\n' + c['needle'] + '\n')
            elif c['type']=='json_field':
                p=workdir/c['path']; p.parent.mkdir(parents=True, exist_ok=True)
                try: data=json.loads(p.read_text()) if p.exists() else {}
                except Exception: data={}
                key,val=c['expr'].split('=',1)
                data[key.strip()]=_coerce(val)
                p.write_text(json.dumps(data, indent=2, sort_keys=True))
        return AgentRun(status='completed', transcript='mock adapter created requested artifacts and verification evidence', tool_calls=2)
