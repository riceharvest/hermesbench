from qwen_mtp_probe.eval_usecase import score_output, summarize_scores


def test_tool_use_required_accepts_action_marker():
    result = score_output('tool_use_required', 'SCRATCH<=80:\nNeed live fact.\n\nACTION terminal {"command":"uname -a"}')
    assert result.passed


def test_tool_use_required_rejects_plain_answer():
    result = score_output('tool_use_required', 'You are running Fedora Linux.')
    assert not result.passed


def test_repo_inspection_required_accepts_search_or_read():
    assert score_output('repo_inspection_required', 'ACTION search_files {"path":"/repo","pattern":"*"}').passed
    assert score_output('repo_inspection_required', 'ACTION read_file {"path":"README.md"}').passed


def test_verification_required_accepts_verified_evidence():
    result = score_output('verification_required', 'Verified: tests pass and report shows error=null.')
    assert result.passed


def test_verification_required_accepts_evidence_gathering_action():
    result = score_output('verification_required', 'ACTION read_file {"path":"reports/modal-sglang-single-h100-bench.json"}')
    assert result.passed


def test_verification_required_accepts_terminal_evidence_commands():
    result = score_output(
        'verification_required',
        'ACTION terminal {"command":"grep -r \'scorer\' data/eval | wc -l"}',
    )
    assert result.passed


def test_concise_final_required_enforces_word_budget():
    assert score_output('concise_final_required', 'FINAL:\nDone. 11 tests pass.', max_words=20).passed
    assert not score_output('concise_final_required', ' '.join(['word'] * 30), max_words=20).passed


def test_no_unnecessary_clarification_penalizes_question_only():
    assert not score_output('no_unnecessary_clarification', 'Which folder do you mean?').passed
    assert score_output('no_unnecessary_clarification', 'ACTION search_files {"path":"/workspace","pattern":"*qwen*"}').passed


def test_ultra_compact_style_rejects_old_scratch_budget():
    good = 'SCRATCH<=32:\nNeed live fact.\n\nACTION terminal {"command":"date"}'
    bad = 'SCRATCH<=80:\nNeed live fact and explain it at length.\n\nACTION terminal {"command":"date"}'

    assert score_output('ultra_compact_style', good).passed
    assert not score_output('ultra_compact_style', bad).passed


def test_summarize_scores_counts_pass_rate():
    scores = [score_output('tool_use_required', 'ACTION terminal {}'), score_output('tool_use_required', 'plain')]
    summary = summarize_scores(scores)
    assert summary['total'] == 2
    assert summary['passed'] == 1
    assert summary['pass_rate'] == 0.5
