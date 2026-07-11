from __future__ import annotations
import argparse, json
from pathlib import Path
from .tasks import validate_tasks, discover_tasks
from .runner import run_benchmark
from .scoring import aggregate
from .versions import list_versions


def _format_size(s):
    if s is None:
        return "unknown"
    try:
        if isinstance(s, str):
            s = float(s)
        if s >= 1_000_000_000:
            return f"{s / 1_000_000_000:.2f}B"
        if s >= 1_000_000:
            return f"{s / 1_000_000:.2f}M"
        if s >= 1_000:
            return f"{s / 1_000:.2f}K"
        return str(int(s))
    except Exception:
        return str(s)


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="hermesbench",
        description="Minimum-capable-model probe for Hermes-style tool-using agents.",
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="run a suite against an agent adapter")
    r.add_argument("--agent", default="hermes")
    r.add_argument("--provider")
    r.add_argument("--model")
    r.add_argument(
        "--profile",
        default="hermesbench",
        help="Hermes profile to use (default: hermesbench)",
    )
    r.add_argument(
        "--reasoning-effort",
        choices=["none", "minimal", "low", "medium", "high", "xhigh", "max"],
    )
    r.add_argument(
        "--suite", default="hermes-core", help="suite to run (default: hermes-core)"
    )
    r.add_argument("--task")
    r.add_argument("--output-dir", default="results")
    r.add_argument("--command")
    r.add_argument("--benchmark-version")
    r.add_argument("--task-root")
    r.add_argument(
        "--model-size",
        type=float,
        help="total parameter count (e.g. 7e9 for 7B) for minimum-capable-model boundary tracking",
    )
    r.add_argument(
        "--jobs", default="auto", help="parallel task workers: auto, 1, or an integer"
    )
    r.add_argument(
        "--quantization", help="quantization level (e.g., Q4_K_M, IQ3_XS, EXL2-4.0bpw)"
    )
    r.add_argument(
        "--stall-idle-seconds",
        type=float,
        default=300.0,
        help="Hermes idle-progress guard in seconds; use 0 to disable",
    )
    r.add_argument(
        "--backend",
        help="local model serving backend (e.g., llama.cpp, vllm, sglang, ollama)",
    )
    s = sub.add_parser("score", help="aggregate a run JSON into a score report")
    s.add_argument("result")
    s.add_argument(
        "--require-capability-pass",
        action="store_true",
        help="exit nonzero unless every required capability task passed with verified telemetry",
    )
    s.add_argument(
        "--min-overall-score",
        type=float,
        help="exit nonzero when overall score is below this fraction (0..1)",
    )
    vt = sub.add_parser(
        "validate-tasks", help="validate task manifests and task quality"
    )
    vt.add_argument("--task-root")
    e = sub.add_parser("export", help="export task prompts as JSONL")
    e.add_argument("--format", choices=["jsonl"], default="jsonl")
    e.add_argument(
        "--suite", default="hermes-core", help="suite to export (default: hermes-core)"
    )
    e.add_argument("--task-root")
    u = sub.add_parser("upload")
    u.add_argument("result")
    u.add_argument("--endpoint")
    u.add_argument("--submission-token")
    u.add_argument("--output-dir", default="submissions")
    u.add_argument("--keep-logs", action="store_true")
    u.add_argument("--print-issue", action="store_true")
    srv = sub.add_parser("serve-api")
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--port", type=int, default=8787)
    srv.add_argument("--store-path", default="submissions/submissions.jsonl")
    srv.add_argument("--submission-token")
    arch = sub.add_parser("archive-official")
    arch.add_argument("--result", required=True)
    arch.add_argument("--manifest", required=True)
    arch.add_argument("--output", required=True)
    sub.add_parser("versions")
    a = p.parse_args(argv)
    if a.cmd == "validate-tasks":
        errs = validate_tasks(task_root=a.task_root)
        quality = validate_tasks(task_root=a.task_root, quality_only=True)
        if errs:
            print("\n".join(errs))
            raise SystemExit(1)
        if quality:
            print("\n".join(quality))
            print(f"ok (with {len(quality)} quality findings)")
        else:
            print("ok")
    elif a.cmd == "run":
        from .scoring import aggregate, is_capability_pass

        result_path = run_benchmark(
            a.agent,
            a.suite,
            a.task,
            a.output_dir,
            a.model,
            a.command,
            a.benchmark_version,
            a.provider,
            a.reasoning_effort,
            a.task_root,
            a.jobs,
            a.quantization,
            a.backend,
            a.profile,
            None if a.stall_idle_seconds == 0 else a.stall_idle_seconds,
        )
        if a.model_size is not None:
            score = aggregate(result_path)
            passed = score["capability_pass"]
            print(f"\n[model-size] {_format_size(a.model_size)} total parameters")
            print(f"[capability-pass] {passed}")
            if not passed:
                print(
                    f"[note] This model did NOT satisfy every required tool class; it is below the minimum-capable boundary."
                )
            else:
                print(
                    f"[note] This model satisfied all required tool classes; it is a candidate for the current minimum-capable-model boundary."
                )
        print(result_path)
    elif a.cmd == "score":
        from .scoring import aggregate

        if a.min_overall_score is not None and not 0 <= a.min_overall_score <= 1:
            p.error("--min-overall-score must be between 0 and 1")
        score = aggregate(a.result)
        print(json.dumps(score, indent=2))
        if a.require_capability_pass and not score["capability_pass"]:
            raise SystemExit(2)
        if (
            a.min_overall_score is not None
            and score["overall_score"] < a.min_overall_score
        ):
            raise SystemExit(2)
    elif a.cmd == "export":
        for t in discover_tasks(a.suite, task_root=a.task_root):
            print(
                json.dumps(
                    {
                        "id": t.metadata["id"],
                        "title": t.metadata["title"],
                        "category": t.metadata["category"],
                        "prompt": t.prompt,
                    }
                )
            )
    elif a.cmd == "upload":
        from .submissions import (
            make_submission_payload,
            post_submission,
            write_submission_file,
        )

        payload = make_submission_payload(a.result, strip_logs=not a.keep_logs)
        if a.endpoint:
            print(
                post_submission(
                    payload, a.endpoint, submission_token=a.submission_token
                )
            )
        elif a.print_issue:
            print(json.dumps(payload["github_issue"], indent=2))
        else:
            path = write_submission_file(payload, a.output_dir)
            print(
                f"wrote sanitized submission {path}\nOpen a GitHub issue using the embedded github_issue payload, or pass --endpoint for a local API."
            )
    elif a.cmd == "serve-api":
        from .http_api import create_app

        create_app(store_path=a.store_path, submission_token=a.submission_token).serve(
            a.host, a.port
        )
    elif a.cmd == "archive-official":
        from .official import archive_official_run

        print(archive_official_run(a.result, a.manifest, a.output))
    elif a.cmd == "versions":
        print(json.dumps(list_versions(), indent=2))


if __name__ == "__main__":
    main()
