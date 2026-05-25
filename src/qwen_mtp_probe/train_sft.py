from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import yaml

from qwen_mtp_probe.datasets import load_chat_jsonl, load_eval_jsonl


def load_sft_config(path: str | Path) -> dict[str, Any]:
    config_path = path if isinstance(path, Path) else Path(path)
    data = yaml.safe_load(config_path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f'{config_path}: expected YAML object')
    for key in ['run_name', 'base_model', 'output_dir', 'training', 'data']:
        if key not in data:
            raise ValueError(f'{config_path}: missing required key {key!r}')
    return data


def summarize_dry_run(config: dict[str, Any]) -> dict[str, Any]:
    data = config['data']
    seed_path = data.get('seed_path') or data.get('train_path')
    eval_path = data['eval_path']
    seed_examples = load_chat_jsonl(seed_path) if seed_path else []
    eval_items = load_eval_jsonl(eval_path)
    return {
        'run_name': config['run_name'],
        'base_model': config['base_model'],
        'output_dir': config['output_dir'],
        'training_method': config['training'].get('method'),
        'adapter': config['training'].get('adapter'),
        'max_seq_length': config['training'].get('max_seq_length'),
        'seed_path': seed_path,
        'eval_path': eval_path,
        'seed_examples': len(seed_examples),
        'eval_items': len(eval_items),
        'would_download_model': False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description='Hermes-agent SFT trainer entrypoint.')
    parser.add_argument('--config', required=True, help='YAML config path')
    parser.add_argument('--dry-run', action='store_true', help='Validate config/data without model download')
    args = parser.parse_args()

    config = load_sft_config(args.config)
    if args.dry_run:
        print(json.dumps(summarize_dry_run(config), indent=2, sort_keys=True))
        return

    raise SystemExit('non-dry-run training is not implemented yet; run with --dry-run')


if __name__ == '__main__':
    main()
