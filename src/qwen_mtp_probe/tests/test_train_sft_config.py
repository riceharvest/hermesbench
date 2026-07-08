from pathlib import Path

from qwen_mtp_probe.train_sft import load_sft_config, summarize_dry_run


def test_load_sft_config_reads_run_name():
    config = load_sft_config(Path('configs/qwen36-hermes-v0-sft.yaml'))
    assert config['run_name'] == 'qwen36-hermes-v0-sft-main'
    assert config['base_model'] == 'unsloth/Qwen3.6-35B-A3B'


def test_summarize_dry_run_counts_seed_rows():
    config = load_sft_config(Path('configs/qwen36-hermes-v0-sft.yaml'))
    summary = summarize_dry_run(config)
    assert summary['run_name'] == 'qwen36-hermes-v0-sft-main'
    assert summary['seed_examples'] >= 5
    assert summary['eval_items'] >= 5
    assert summary['would_download_model'] is False


def test_summarize_dry_run_prefers_processed_train_path_when_present(tmp_path):
    train_path = tmp_path / 'train.jsonl'
    train_path.write_text(
        '{"messages":[{"role":"system","content":"s"},'
        '{"role":"user","content":"u"},'
        '{"role":"assistant","content":"ACTION terminal {\\"command\\":\\"date\\"}"}]}\n'
    )
    config = load_sft_config(Path('configs/qwen36-hermes-v0-sft.yaml'))
    config['data'] = dict(config['data'], train_path=str(train_path))

    summary = summarize_dry_run(config)

    assert summary['train_path'] == str(train_path)
    assert summary['train_examples'] == 1
