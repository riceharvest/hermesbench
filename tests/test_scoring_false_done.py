import json

from hermesbench.scoring import aggregate


def test_false_done_zeroes_effective_score_in_aggregate(tmp_path):
    result = tmp_path / 'result.json'
    result.write_text(json.dumps({
        'schema_version': 'hermesbench.result.v1',
        'run_id': 'r',
        'suite': 'public-dev',
        'agent': 'hermes',
        'model': 'm',
        'started_at': 's',
        'completed_at': 'c',
        'metadata': {},
        'results': [
            {'task_id': 'a', 'category': 'hard', 'status': 'failed', 'score': 0.9, 'passed': False, 'false_done': True, 'wall_time_seconds': 1},
            {'task_id': 'b', 'category': 'hard', 'status': 'passed', 'score': 1.0, 'passed': True, 'false_done': False, 'wall_time_seconds': 1},
        ],
    }))

    score = aggregate(result)

    assert score['overall_score'] == 0.5
    assert score['category_scores']['hard'] == 0.5
    assert score['raw_overall_score'] == 0.95
    assert score['false_done_rate'] == 0.5
