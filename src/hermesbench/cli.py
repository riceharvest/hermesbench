from __future__ import annotations
import argparse, json
from pathlib import Path
from .tasks import validate_tasks, discover_tasks
from .runner import run_benchmark
from .scoring import aggregate
from .versions import list_versions

def main(argv=None):
    p=argparse.ArgumentParser(prog='hermesbench')
    sub=p.add_subparsers(dest='cmd', required=True)
    r=sub.add_parser('run'); r.add_argument('--agent', default='mock'); r.add_argument('--model'); r.add_argument('--suite', default='public-dev'); r.add_argument('--task'); r.add_argument('--output-dir', default='results'); r.add_argument('--command'); r.add_argument('--benchmark-version')
    s=sub.add_parser('score'); s.add_argument('result')
    sub.add_parser('validate-tasks')
    e=sub.add_parser('export'); e.add_argument('--format', choices=['jsonl'], default='jsonl')
    u=sub.add_parser('upload'); u.add_argument('result')
    srv=sub.add_parser('serve-api'); srv.add_argument('--host', default='127.0.0.1'); srv.add_argument('--port', type=int, default=8787); srv.add_argument('--store-path', default='submissions/submissions.jsonl'); srv.add_argument('--submission-token')
    arch=sub.add_parser('archive-official'); arch.add_argument('--result', required=True); arch.add_argument('--manifest', required=True); arch.add_argument('--output', required=True)
    sub.add_parser('versions')
    a=p.parse_args(argv)
    if a.cmd=='validate-tasks':
        errs=validate_tasks();
        if errs: print('\n'.join(errs)); raise SystemExit(1)
        print('ok')
    elif a.cmd=='run': print(run_benchmark(a.agent,a.suite,a.task,a.output_dir,a.model,a.command,a.benchmark_version))
    elif a.cmd=='score': print(json.dumps(aggregate(a.result), indent=2))
    elif a.cmd=='export':
        for t in discover_tasks(): print(json.dumps({'id':t.metadata['id'],'title':t.metadata['title'],'category':t.metadata['category'],'prompt':t.prompt}))
    elif a.cmd=='upload': print('Upload API is scaffolded; see docs/api.md. Validated result ready: '+a.result)
    elif a.cmd=='serve-api':
        from .http_api import create_app
        create_app(store_path=a.store_path, submission_token=a.submission_token).serve(a.host, a.port)
    elif a.cmd=='archive-official':
        from .official import archive_official_run
        print(archive_official_run(a.result, a.manifest, a.output))
    elif a.cmd=='versions': print(json.dumps(list_versions(), indent=2))
if __name__=='__main__': main()
