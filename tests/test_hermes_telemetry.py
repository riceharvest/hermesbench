import json

from hermesbench.adapters.hermes import extract_hermes_telemetry
from hermesbench.scoring import aggregate


def test_extracts_telemetry_from_stdout_json_summary():
    transcript = """
Hermes Agent finished.
{"type":"summary","tool_call_count":4,"usage":{"prompt_tokens":123,"completion_tokens":45,"total_tokens":168},"cost_usd":0.0123}
"""
    telemetry = extract_hermes_telemetry(transcript)
    assert telemetry.tool_calls == 4
    assert telemetry.token_usage == {"prompt_tokens": 123, "completion_tokens": 45, "total_tokens": 168}
    assert telemetry.cost_usd == 0.0123


def test_extracts_telemetry_from_session_jsonl_snippet():
    session = "\n".join([
        json.dumps({"event":"tool_call","name":"terminal"}),
        json.dumps({"type":"response.completed","response":{"usage":{"input_tokens":10,"output_tokens":7}, "cost_usd": 0.002}}),
        json.dumps({"event":"tool_call","tool":"file"}),
    ])
    telemetry = extract_hermes_telemetry(session)
    assert telemetry.tool_calls == 2
    assert telemetry.token_usage == {"input_tokens": 10, "output_tokens": 7}
    assert telemetry.cost_usd == 0.002


def test_extracts_telemetry_from_hermes_human_logs():
    log = """
2026-06-01 INFO [session] agent.conversation_loop: API call #1: model=gpt-5.5 provider=openai-codex in=7459 out=52 total=7511 latency=2.4s
2026-06-01 INFO [session] agent.tool_executor: tool read_file completed (0.87s, 506 chars)
2026-06-01 INFO [session] agent.conversation_loop: API call #2: model=gpt-5.5 provider=openai-codex in=7690 out=173 total=7863 latency=4.0s
2026-06-01 INFO [session] agent.tool_executor: tool write_file completed (0.12s, 337 chars)
"""
    telemetry = extract_hermes_telemetry(log)
    assert telemetry.tool_calls == 2
    assert telemetry.token_usage == {"input_tokens": 15149, "output_tokens": 225, "total_tokens": 15374}


def test_aggregate_preserves_old_files_and_sums_new_token_usage(tmp_path):
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        "schema_version":"hermesbench.result.v1",
        "run_id":"abc",
        "suite":"public-dev",
        "agent":"hermes",
        "model":"m",
        "started_at":"s",
        "completed_at":"c",
        "results":[
            {"task_id":"t1","category":"cat","status":"passed","score":1,"passed":True,"wall_time_seconds":1,"tool_calls":3,"token_usage":{"input_tokens":10,"output_tokens":5},"cost_usd":0.01},
            {"task_id":"t2","category":"cat","status":"failed","score":0,"passed":False,"wall_time_seconds":2}
        ],
        "metadata":{}
    }))
    score = aggregate(result)
    assert score["tool_call_count"] == 3
    assert score["token_usage"] == {"input_tokens": 10, "output_tokens": 5}
    assert score["total_tokens"] == 15
