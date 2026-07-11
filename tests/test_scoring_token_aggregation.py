import json

from hermesbench.scoring import aggregate


def test_token_aggregation_full_usage(tmp_path):
    """All token categories present; verify per-field aggregates."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'tokens-full',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': '2026-07-10T12:00:00',
        'completed_at': '2026-07-10T12:05:30',
        'metadata': {},
        'results': [
            {
                'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 60,
                'token_usage': {
                    'prompt_tokens': 500,
                    'cached_prompt_tokens': 200,
                    'completion_tokens': 300,
                    'reasoning_tokens': 100,
                    'tool_call_tokens': 50,
                    'total_tokens': 950,
                    'input_tokens_cache_read': 200,
                },
            },
            {
                'task_id': 'b', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 120,
                'token_usage': {
                    'prompt_tokens': 1000,
                    'cached_prompt_tokens': 400,
                    'completion_tokens': 600,
                    'reasoning_tokens': 200,
                    'tool_call_tokens': 100,
                    'total_tokens': 2000,
                    'input_tokens_cache_read': 400,
                },
            },
        ],
    }))

    score = aggregate(result)

    # ── Token field aggregates ───────────────────────────────────────────
    assert score['prompt_tokens'] == 1500
    assert score['cached_prompt_tokens'] == 600
    assert score['completion_tokens'] == 900
    assert score['reasoning_tokens'] == 300
    assert score['tool_call_tokens'] == 150
    assert score['explicit_total_tokens'] == 2950
    # backward compat
    assert score['input_tokens'] == 1500
    assert score['output_tokens'] == 900
    assert score['total_tokens'] == 2950
    # token meta
    assert score['input_tokens_cache_read'] == 600
    assert score['input_tokens_cache_write'] is None
    assert score['token_source'] is None

    # ── Per-task averages ────────────────────────────────────────────────
    assert score['tokens_per_task'] == 1475.0
    assert score['tokens_per_successful_task'] == 1475.0
    assert score['prompt_tokens_per_task'] == 750.0
    assert score['completion_tokens_per_task'] == 450.0
    assert score['reasoning_tokens_per_task'] == 150.0
    assert score['tool_call_tokens_per_task'] == 75.0

    # ── Run duration ─────────────────────────────────────────────────────
    assert score['run_duration_seconds'] == 330  # 5 min 30 sec

    # ── Throughput ───────────────────────────────────────────────────────
    assert score['tasks_per_second'] == 2 / 330
    assert score['tokens_per_second'] == 2950 / 330

    # ── Wall time (existing + new) ───────────────────────────────────────
    assert score['total_execution_time_seconds'] == 180
    assert score['sum_wall_time_seconds'] == 180
    assert score['p95_wall_time_seconds'] == 120
    assert score['median_wall_time_seconds'] == 90.0
    assert score['mean_wall_time_seconds'] == 90.0
    assert score['min_wall_time_seconds'] == 60
    assert score['max_wall_time_seconds'] == 120


def test_token_aggregation_partial_usage(tmp_path):
    """Only some token categories present; missing ones remain None."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'tokens-partial',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {
                'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 10,
                'token_usage': {
                    'input_tokens': 100,
                    'output_tokens': 50,
                },
            },
            {
                'task_id': 'b', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 20,
                'token_usage': {
                    'input_tokens': 200,
                    'output_tokens': 100,
                },
            },
        ],
    }))

    score = aggregate(result)

    # Present fields get summed
    assert score['prompt_tokens'] == 300   # maps from input_tokens
    assert score['completion_tokens'] == 150  # maps from output_tokens
    assert score['total_tokens'] is not None  # fallback sum of any *token* key

    # Missing fields stay None
    assert score['cached_prompt_tokens'] is None
    assert score['reasoning_tokens'] is None
    assert score['tool_call_tokens'] is None
    assert score['explicit_total_tokens'] is None
    assert score['input_tokens_cache_read'] is None
    assert score['input_tokens_cache_write'] is None
    assert score['token_source'] is None

    # Per-task averages for missing fields
    assert score['prompt_tokens_per_task'] == 150.0
    assert score['completion_tokens_per_task'] == 75.0
    assert score['reasoning_tokens_per_task'] is None
    assert score['tool_call_tokens_per_task'] is None

    # Run duration unavailable (unparseable timestamps)
    assert score['run_duration_seconds'] is None

    # Throughput unavailable when run_duration missing
    assert score['tasks_per_second'] is None
    assert score['tokens_per_second'] is None


def test_token_aggregation_no_tokens_at_all(tmp_path):
    """No token_usage anywhere; everything stays None."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'no-tokens',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0, 'passed': True, 'wall_time_seconds': 10},
            {'task_id': 'b', 'category': 'cat', 'status': 'passed', 'score': 1.0, 'passed': True, 'wall_time_seconds': 20},
        ],
    }))

    score = aggregate(result)

    assert score['prompt_tokens'] is None
    assert score['cached_prompt_tokens'] is None
    assert score['completion_tokens'] is None
    assert score['reasoning_tokens'] is None
    assert score['tool_call_tokens'] is None
    assert score['explicit_total_tokens'] is None
    assert score['total_tokens'] is None
    assert score['input_tokens'] is None
    assert score['output_tokens'] is None
    assert score['tokens_per_task'] is None
    assert score['tokens_per_successful_task'] is None
    assert score['prompt_tokens_per_task'] is None
    assert score['completion_tokens_per_task'] is None
    assert score['reasoning_tokens_per_task'] is None
    assert score['tool_call_tokens_per_task'] is None
    assert score['tokens_per_second'] is None


def test_run_duration_parseable_timestamps(tmp_path):
    """run_duration_seconds computed from ISO timestamps."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'duration-test',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': '2026-01-15T10:30:00',
        'completed_at': '2026-01-15T10:35:15.500',
        'metadata': {},
        'results': [
            {'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0, 'passed': True, 'wall_time_seconds': 5},
        ],
    }))

    score = aggregate(result)
    assert score['run_duration_seconds'] == 315.5  # 5 min 15.5 sec
    assert score['tasks_per_second'] == 1 / 315.5

    # No tokens => tokens_per_second is None despite run_duration being available
    assert score['tokens_per_second'] is None


def test_run_duration_unparseable_timestamps(tmp_path):
    """Non-ISO/empty timestamps -> run_duration is None."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'unparseable',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0, 'passed': True, 'wall_time_seconds': 10},
        ],
    }))

    score = aggregate(result)
    assert score['run_duration_seconds'] is None
    assert score['tasks_per_second'] is None
    assert score['tokens_per_second'] is None


def test_token_usage_with_alias_input_output_keys(tmp_path):
    """Token fields using 'input_tokens'/'output_tokens' aliases get mapped correctly."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'alias-test',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {
                'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 10,
                'token_usage': {
                    'input_tokens': 100,
                    'output_tokens': 50,
                    'cached_input_tokens': 30,
                },
            },
        ],
    }))

    score = aggregate(result)
    assert score['prompt_tokens'] == 100
    assert score['completion_tokens'] == 50
    assert score['cached_prompt_tokens'] == 30
    assert score['input_tokens'] == 100
    assert score['output_tokens'] == 50


def test_mixed_token_usage_missing_in_some_tasks(tmp_path):
    """Some tasks have token_usage, others don't — aggregation handles this."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'mixed',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {
                'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 10,
                'token_usage': {'prompt_tokens': 100, 'completion_tokens': 50, 'total_tokens': 150},
            },
            {
                'task_id': 'b', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 20,
                # no token_usage at all
            },
        ],
    }))

    score = aggregate(result)

    # Task a contributes 100 prompt + 50 completion; task b contributes nothing
    assert score['prompt_tokens'] == 100
    assert score['completion_tokens'] == 50
    assert score['explicit_total_tokens'] == 150
    assert score['cached_prompt_tokens'] is None
    assert score['reasoning_tokens'] is None

    # Per-task averages: only task a counts as having data
    assert score['prompt_tokens_per_task'] == 50.0  # 100 / 2
    assert score['completion_tokens_per_task'] == 25.0  # 50 / 2


# ── token_source retention tests ─────────────────────────────────────────


def test_token_source_single_string(tmp_path):
    """token_source is a single string — retained as a deterministic list."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'source-str',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': '2026-07-10T12:00:00',
        'completed_at': '2026-07-10T12:05:00',
        'metadata': {},
        'results': [
            {
                'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 10,
                'token_usage': {
                    'prompt_tokens': 100, 'completion_tokens': 50,
                    'token_source': 'openai',
                },
            },
            {
                'task_id': 'b', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 20,
                'token_usage': {
                    'prompt_tokens': 200, 'completion_tokens': 100,
                    'token_source': 'openai',
                },
            },
        ],
    }))

    score = aggregate(result)
    # token_source is a sorted list of unique sources
    assert score['token_source'] == ['openai']
    # Numeric fields still work
    assert score['prompt_tokens'] == 300
    assert score['completion_tokens'] == 150


def test_token_source_multiple_values(tmp_path):
    """Different token_source values across tasks — retained as sorted list."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'source-multi',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {
                'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 10,
                'token_usage': {
                    'prompt_tokens': 100,
                    'token_source': 'tiktoken',
                },
            },
            {
                'task_id': 'b', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 20,
                'token_usage': {
                    'prompt_tokens': 200,
                    'token_source': 'openai',
                },
            },
            {
                'task_id': 'c', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 30,
                'token_usage': {
                    'prompt_tokens': 300,
                    'token_source': 'tiktoken',  # duplicate
                },
            },
        ],
    }))

    score = aggregate(result)
    assert score['token_source'] == ['openai', 'tiktoken']  # sorted
    assert score['prompt_tokens'] == 600


def test_token_source_list_value(tmp_path):
    """token_source as a list of strings — items are collected."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'source-list',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {
                'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 10,
                'token_usage': {
                    'token_source': ['tiktoken', 'openai'],
                },
            },
        ],
    }))

    score = aggregate(result)
    assert score['token_source'] == ['openai', 'tiktoken']


def test_token_source_missing_is_none(tmp_path):
    """No token_source anywhere -> token_source is None (preserves null semantics)."""
    result = tmp_path / "result.json"
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'source-none',
        'suite': 'natural-tools-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {
                'task_id': 'a', 'category': 'cat', 'status': 'passed', 'score': 1.0,
                'passed': True, 'wall_time_seconds': 10,
                'token_usage': {'prompt_tokens': 100},
            },
        ],
    }))

    score = aggregate(result)
    assert score['token_source'] is None
