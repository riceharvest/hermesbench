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
    def run_task(self, task, workdir: Path, hidden_dir: Path | None = None) -> AgentRun:
        if hidden_dir is not None and (hidden_dir/'expected_state.json').exists():
            expected=json.loads((hidden_dir/'expected_state.json').read_text())
            state_path=workdir/'case'/'project_state.json'
            state_path.parent.mkdir(parents=True, exist_ok=True)
            state_path.write_text(json.dumps(expected.get('state', {}), indent=2, sort_keys=True))
            artifacts=workdir/'artifacts'; artifacts.mkdir(parents=True, exist_ok=True)
            report=expected.get('report', {}) | {
                'task_id': task.metadata['id'],
                'category': task.metadata['category'],
                'verified': True,
            }
            (artifacts/'final_report.json').write_text(json.dumps(report, indent=2, sort_keys=True))
            checkpoint=expected.get('checkpoint', {})
            checkpoint_lines=['# ProjectOps checkpoint'] + [f'- {k}: {v}' for k,v in sorted(checkpoint.items())]
            checkpoint_lines.append('- verification_status: PASS')
            (artifacts/'checkpoint.md').write_text('\n'.join(checkpoint_lines)+'\n')
            actions=expected.get('action_log', [{'episode':'mock','action':'verify','result':'PASS'}])
            (artifacts/'action_log.jsonl').write_text('\n'.join(json.dumps(a, sort_keys=True) for a in actions)+'\n')
            return AgentRun(status='completed', transcript='mock adapter applied hidden ProjectOps oracle and verified final state', tool_calls=8, behavior_evidence_trusted=True)
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
                key=next((c['expr'].split(op,1)[0] for op in ['~=','>=','<=','!=','>','<','='] if op in c['expr']), c['expr']).strip()
                val=next((c['expr'].split(op,1)[1] for op in ['~=','>=','<=','!=','>','<','='] if op in c['expr']), 'true')
                cur=data
                parts=key.split('.')
                for part in parts[:-1]:
                    cur=cur.setdefault(part,{})
                cur[parts[-1]]=_coerce(val.split('±',1)[0].split('+/-',1)[0])
                p.write_text(json.dumps(data, indent=2, sort_keys=True))
            elif c['type']=='glob_exists':
                pattern=c.get('pattern','artifact.txt').replace('*','mock')
                p=workdir/pattern; p.parent.mkdir(parents=True, exist_ok=True); p.write_text('mock glob artifact\n')
            elif c['type']=='artifact_matches':
                p=workdir/c['path']; p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text((p.read_text() if p.exists() else '') + '\n' + c.get('pattern','mock').strip('^$') + '\n')
        # Emit fake telemetry for the required tool classes so the behavior grader sees them.
        tool_class_to_name = {
            'file': 'read_file', 'terminal': 'terminal', 'web': 'web_search',
            'browser': 'browser_navigate', 'browser_cdp': 'browser_cdp', 'code_execution': 'execute_code',
            'vision': 'vision_analyze', 'image_gen': 'image_gen', 'video': 'video_analyze',
            'video_gen': 'video_generate', 'tts': 'text_to_speech', 'memory': 'memory',
            'todo': 'todo', 'skills': 'skill_view', 'session_search': 'session_search',
            'semantic_search': 'semantic_search', 'delegation': 'delegate_task', 'clarify': 'clarify',
            'cronjob': 'cronjob', 'computer_use': 'computer_use', 'homeassistant': 'ha_list_entities',
            'kanban': 'kanban_show', 'project': 'project_list', 'discord': 'discord',
            'x_search': 'x_search', 'yuanbao': 'yb_query_group_info', 'spotify': 'spotify_search',
            'feishu': 'feishu_doc_read', 'messaging': 'send_message',
            'discord_admin': 'discord_admin',
            'stt': 'speech_to_text', 'obsidian': 'obsidian_read', 'github': 'github',
            'docker': 'docker_ps', 'notion': 'notion_page_read', 'linear': 'linear_search',
            'maps': 'maps_geocode', 'himalaya': 'himalaya_list', 'openhue': 'openhue_light_set',
        }
        required = task.metadata.get('tool_use_requirements', []) or []
        telemetry_lines = []
        for cls in required:
            name = tool_class_to_name.get(cls, cls)
            telemetry_lines.append(f'agent.tool_executor: tool {name} completed (task={task.metadata["id"]})')
        transcript = 'mock adapter created requested artifacts and verification evidence\n' + '\n'.join(telemetry_lines)
        return AgentRun(status='completed', transcript=transcript, tool_calls=len(required), behavior_evidence_trusted=True)
