import json

from hermesbench.graders.deterministic import run_checks


def test_json_field_failure_evidence_names_expression(tmp_path):
    artifact = tmp_path / 'report.json'
    artifact.write_text(json.dumps({'expected_total': 573.5}))

    score, evidence = run_checks(tmp_path, [
        {'type': 'json_field', 'path': 'report.json', 'expr': 'expected_total=574.5'}
    ])

    assert score == 0
    assert evidence == ['json_field report.json expected_total=574.5: FAIL (actual=573.5)']
