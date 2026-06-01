import json

from hermesbench.scoring import aggregate


def test_aggregate_exposes_pinchbench_style_and_agent_metrics(tmp_path):
    result = tmp_path / 'result.json'
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'metrics',
        'suite': 'public-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {'provider': 'p', 'reasoning_effort': 'low'},
        'results': [
            {'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1, 'passed': True, 'wall_time_seconds': 10, 'tool_calls': 2, 'token_usage': {'input_tokens': 100, 'output_tokens': 20, 'total_tokens': 120}, 'cost_usd': 0.5, 'verification_evidence': ['ok']},
            {'task_id': 'b', 'category': 'cat', 'status': 'failed', 'score': 0.75, 'passed': False, 'wall_time_seconds': 30, 'tool_calls': 4, 'token_usage': {'input_tokens': 50, 'output_tokens': 10, 'total_tokens': 60}, 'cost_usd': 0.25, 'false_done': True, 'timeout': True},
        ],
    }))

    score = aggregate(result)

    assert score['total_score'] == 1.0
    assert score['raw_total_score'] == 1.75
    assert score['max_score'] == 2
    assert score['score_percentage'] == 0.5
    assert score['total_execution_time_seconds'] == 40
    assert score['mean_wall_time_seconds'] == 20
    assert score['min_wall_time_seconds'] == 10
    assert score['max_wall_time_seconds'] == 30
    assert score['p95_wall_time_seconds'] == 30
    assert score['avg_tool_calls_per_task'] == 3
    assert score['cost_per_task_usd'] == 0.375
    assert score['cost_per_successful_task_usd'] == 0.5
    assert score['score_per_dollar'] == 100 * 0.5 / 0.75
    assert score['tokens_per_successful_task'] == 180
    assert score['input_tokens'] == 150
    assert score['output_tokens'] == 30
