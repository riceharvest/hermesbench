import pytest

from qwen_mtp_probe.datasets import load_chat_jsonl, load_eval_jsonl


def test_load_chat_jsonl_accepts_seed_examples():
    rows = load_chat_jsonl('data/examples/hermes_compact_traces.seed.jsonl')
    assert len(rows) >= 5
    assert rows[0].messages[-1].role == 'assistant'
    assert 'ACTION' in rows[0].messages[-1].content


def test_load_chat_jsonl_rejects_missing_messages(tmp_path):
    path = tmp_path / 'bad.jsonl'
    path.write_text('{"text":"no messages"}\n')
    with pytest.raises(ValueError, match='messages'):
        load_chat_jsonl(path)


def test_load_chat_jsonl_rejects_bad_role(tmp_path):
    path = tmp_path / 'bad-role.jsonl'
    path.write_text('{"messages":[{"role":"alien","content":"x"}]}\n')
    with pytest.raises(ValueError, match='role'):
        load_chat_jsonl(path)


def test_load_eval_jsonl_accepts_seed_eval():
    rows = load_eval_jsonl('data/eval/hermes_v0_eval.seed.jsonl')
    assert len(rows) >= 5
    assert rows[0].id
    assert rows[0].scorer == 'tool_use_required'


def test_load_eval_jsonl_rejects_missing_required_keys(tmp_path):
    path = tmp_path / 'bad-eval.jsonl'
    path.write_text('{"id":"x","input":"missing"}\n')
    with pytest.raises(ValueError, match='expected_behavior'):
        load_eval_jsonl(path)
