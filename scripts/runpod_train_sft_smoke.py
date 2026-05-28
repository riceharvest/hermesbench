#!/usr/bin/env python3
"""RunPod-compatible Qwen3.6 Hermes SFT smoke trainer.

This mirrors the Modal smoke trainer but has no Modal dependency and writes unique
artifacts for each run so stale reports cannot be mistaken for fresh results.
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

MODEL_NAME = 'unsloth/Qwen3.6-35B-A3B'
DEFAULT_CONFIG_PATH = Path('configs/qwen36-hermes-v0-sft.yaml')
DEFAULT_TRAIN_PATH = Path('data/processed/hermes_v0_train.jsonl')
DEFAULT_EVAL_PATH = Path('data/eval/hermes_v0_eval.jsonl')


def _load_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open() as handle:
        for line in handle:
            if not line.strip():
                continue
            rows.append(json.loads(line))
            if limit is not None and len(rows) >= limit:
                break
    return rows


def _format_messages(tokenizer: Any, row: dict[str, Any]) -> str:
    messages = row.get('messages')
    if not isinstance(messages, list):
        raise ValueError('expected row.messages list')
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    except Exception:
        parts: list[str] = []
        for message in messages:
            role = message.get('role', 'unknown')
            content = message.get('content', '')
            parts.append(f'{role.upper()}: {content}')
        return '\n'.join(parts) + '\n'


def _tokenize_rows(tokenizer: Any, rows: list[dict[str, Any]], max_seq_length: int) -> list[dict[str, Any]]:
    tokenized: list[dict[str, Any]] = []
    eos = tokenizer.eos_token or ''
    for row in rows:
        messages = row.get('messages')
        if not isinstance(messages, list) or not messages or messages[-1].get('role') != 'assistant':
            continue
        assistant_content = str(messages[-1].get('content', '')).strip()
        if not assistant_content:
            continue
        prompt_messages = messages[:-1]
        try:
            prompt = tokenizer.apply_chat_template(
                prompt_messages,
                tokenize=False,
                add_generation_prompt=True,
            )
        except Exception:
            prompt = _format_messages(tokenizer, {'messages': prompt_messages}) + 'ASSISTANT: '
        target = assistant_content + eos
        prompt_ids = tokenizer(prompt, add_special_tokens=False)['input_ids']
        target_ids = tokenizer(target, add_special_tokens=False)['input_ids']
        input_ids = (prompt_ids + target_ids)[:max_seq_length]
        label_start = min(len(prompt_ids), len(input_ids))
        labels = [-100] * label_start + input_ids[label_start:]
        if not any(label != -100 for label in labels):
            continue
        tokenized.append(
            {
                'input_ids': input_ids,
                'attention_mask': [1] * len(input_ids),
                'labels': labels,
                'label_tokens': sum(label != -100 for label in labels),
            }
        )
    if not tokenized:
        raise ValueError('no usable tokenized examples')
    return tokenized


def _collate(tokenizer: Any, features: list[dict[str, Any]]) -> dict[str, Any]:
    import torch

    max_len = max(len(feature['input_ids']) for feature in features)
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    input_ids: list[list[int]] = []
    attention_mask: list[list[int]] = []
    labels: list[list[int]] = []
    for feature in features:
        pad = max_len - len(feature['input_ids'])
        input_ids.append(feature['input_ids'] + [pad_id] * pad)
        attention_mask.append(feature['attention_mask'] + [0] * pad)
        labels.append(feature['labels'] + [-100] * pad)
    return {
        'input_ids': torch.tensor(input_ids, dtype=torch.long),
        'attention_mask': torch.tensor(attention_mask, dtype=torch.long),
        'labels': torch.tensor(labels, dtype=torch.long),
    }


def _make_run_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return f'{prefix}-{stamp}-{os.getpid()}'


def run_smoke(args: argparse.Namespace) -> dict[str, Any]:
    started = time.time()
    run_id = args.run_id or _make_run_id('runpod-sft-smoke')
    output_dir = Path(args.output_root) / run_id
    report_path = Path(args.report_root) / f'{run_id}.json'
    report: dict[str, Any] = {
        'stage': 'start',
        'runner': 'runpod',
        'run_id': run_id,
        'base_model': MODEL_NAME,
        'model': args.model_name,
        'max_steps': args.max_steps,
        'max_seq_length': args.max_seq_length,
        'train_limit': args.train_limit,
        'learning_rate': args.learning_rate,
        'lora_r': args.lora_r,
        'lora_alpha': args.lora_alpha,
        'grad_accum': args.grad_accum,
        'eval_limit': args.eval_limit,
        'max_train_tokens': args.max_train_tokens,
        'output_dir': str(output_dir),
        'report_path': str(report_path),
        'error': None,
    }

    try:
        import torch
        import yaml
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from qwen_mtp_probe.modal_smoke_eval import evaluate_smoke_generations, select_smoke_eval_items
        from qwen_mtp_probe.modal_training_token_filter import filter_tokenized_examples_by_length
        from torch.utils.data import DataLoader
        from transformers import AutoModelForCausalLM, AutoTokenizer

        torch.manual_seed(args.seed)
        gpu_names = [torch.cuda.get_device_name(i) for i in range(torch.cuda.device_count())]
        print('[sft-smoke] torch', torch.__version__, 'cuda', torch.version.cuda, flush=True)
        print('[sft-smoke] gpus', gpu_names, flush=True)
        report.update({'torch': torch.__version__, 'cuda': torch.version.cuda, 'gpus': gpu_names})

        config = yaml.safe_load(Path(args.config).read_text())
        rows = _load_jsonl(Path(args.train), limit=args.train_limit)
        report.update({'stage': 'data', 'loaded_rows': len(rows), 'config_run_name': config['run_name']})
        print(f'[sft-smoke] loaded {len(rows)} rows', flush=True)

        tokenizer = AutoTokenizer.from_pretrained(args.model_name, trust_remote_code=True)
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = 'right'

        tokenized = _tokenize_rows(tokenizer, rows, max_seq_length=args.max_seq_length)
        tokenized, token_filter_stats = filter_tokenized_examples_by_length(
            tokenized,
            max_tokens=args.max_train_tokens,
        )
        if not tokenized:
            raise ValueError('no usable tokenized examples after token budget filter')
        lengths = [len(row['input_ids']) for row in tokenized]
        label_lengths = [int(row.get('label_tokens', 0)) for row in tokenized]
        report.update(
            {
                'stage': 'tokenized',
                'tokenized_rows': len(tokenized),
                'min_tokens': min(lengths),
                'max_tokens': max(lengths),
                'avg_tokens': sum(lengths) / len(lengths),
                'min_label_tokens': min(label_lengths),
                'max_label_tokens': max(label_lengths),
                'avg_label_tokens': sum(label_lengths) / len(label_lengths),
                'label_masking': 'assistant_only',
                'token_filter': token_filter_stats,
            }
        )
        print('[sft-smoke] tokenized', report['tokenized_rows'], 'avg_tokens', report['avg_tokens'], flush=True)

        model = AutoModelForCausalLM.from_pretrained(
            args.model_name,
            torch_dtype='auto',
            device_map='auto',
            trust_remote_code=True,
            low_cpu_mem_usage=True,
        )
        model.config.use_cache = False
        model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)

        lora_modules = [m for m in config['lora']['target_modules'] if 'router' not in m.lower()]
        peft_config = LoraConfig(
            r=args.lora_r,
            lora_alpha=args.lora_alpha,
            lora_dropout=float(config['lora'].get('dropout', 0.05)),
            bias='none',
            task_type='CAUSAL_LM',
            target_modules=lora_modules,
        )
        model = get_peft_model(model, peft_config)
        model.train()
        trainable_params, all_params = model.get_nb_trainable_parameters()
        report.update(
            {
                'stage': 'model_loaded',
                'target_modules': lora_modules,
                'trainable_params': int(trainable_params),
                'all_params': int(all_params),
                'trainable_percent': float(trainable_params / all_params * 100),
                'cuda_memory_allocated_gb_loaded': torch.cuda.memory_allocated() / 1e9,
                'cuda_memory_reserved_gb_loaded': torch.cuda.memory_reserved() / 1e9,
            }
        )
        print('[sft-smoke] trainable', trainable_params, 'of', all_params, flush=True)

        loader = DataLoader(
            tokenized,
            batch_size=1,
            shuffle=True,
            collate_fn=lambda features: _collate(tokenizer, features),
        )
        optimizer = torch.optim.AdamW(model.parameters(), lr=args.learning_rate)
        step_losses: list[float] = []
        optimizer_steps = 0
        micro_steps = 0
        optimizer.zero_grad(set_to_none=True)

        while optimizer_steps < args.max_steps:
            for batch in loader:
                batch = {key: value.to(model.device) for key, value in batch.items()}
                outputs = model(**batch)
                loss = outputs.loss / args.grad_accum
                loss.backward()
                micro_steps += 1
                if micro_steps % args.grad_accum == 0:
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
                    optimizer_steps += 1
                    value = float((loss.detach() * args.grad_accum).cpu())
                    step_losses.append(value)
                    print(f'[sft-smoke] step {optimizer_steps}/{args.max_steps} loss={value:.4f}', flush=True)
                    if optimizer_steps >= args.max_steps:
                        break

        output_dir.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(output_dir)
        tokenizer.save_pretrained(output_dir)
        model.eval()

        def generate_for_user(user_input: str) -> str:
            prompt_messages = [
                {'role': 'system', 'content': 'You are Hermes Agent. Use ultra-compact actions. No fake verification.'},
                {'role': 'user', 'content': user_input},
            ]
            prompt = tokenizer.apply_chat_template(prompt_messages, tokenize=False, add_generation_prompt=True)
            inputs = tokenizer(prompt, return_tensors='pt').to(model.device)
            with torch.no_grad():
                output_ids = model.generate(**inputs, max_new_tokens=64, do_sample=False, use_cache=True)
            return tokenizer.decode(output_ids[0][inputs['input_ids'].shape[1] :], skip_special_tokens=True).strip()

        smoke_generation = generate_for_user('what time is it right now?')
        eval_items = select_smoke_eval_items(_load_jsonl(Path(args.eval)), limit=args.eval_limit)
        eval_generations = {str(item['id']): generate_for_user(str(item['input'])) for item in eval_items}
        smoke_eval = evaluate_smoke_generations(eval_items, eval_generations)
        smoke_eval['scorer_counts'] = eval_items.scorer_counts

        report.update(
            {
                'stage': 'done',
                'optimizer_steps': optimizer_steps,
                'micro_steps': micro_steps,
                'initial_loss': step_losses[0] if step_losses else None,
                'final_loss': step_losses[-1] if step_losses else None,
                'loss_delta': (step_losses[0] - step_losses[-1]) if len(step_losses) >= 2 else None,
                'step_losses_tail': step_losses[-20:],
                'adapter_dir': str(output_dir),
                'smoke_generation': smoke_generation,
                'smoke_eval': smoke_eval,
                'cuda_memory_allocated_gb_final': torch.cuda.memory_allocated() / 1e9,
                'cuda_memory_reserved_gb_final': torch.cuda.memory_reserved() / 1e9,
                'elapsed_seconds': time.time() - started,
            }
        )
        print('[sft-smoke] done', json.dumps({k: report[k] for k in ['initial_loss', 'final_loss', 'loss_delta']}), flush=True)

    except Exception as exc:
        report.update({'stage': report.get('stage', 'error'), 'error': repr(exc), 'elapsed_seconds': time.time() - started})
        print('[sft-smoke] ERROR', repr(exc), flush=True)

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print('[sft-smoke] report', report_path, flush=True)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default=str(DEFAULT_CONFIG_PATH))
    parser.add_argument('--train', default=str(DEFAULT_TRAIN_PATH))
    parser.add_argument('--eval', default=str(DEFAULT_EVAL_PATH))
    parser.add_argument('--model-name', default=MODEL_NAME)
    parser.add_argument('--max-steps', type=int, default=60)
    parser.add_argument('--max-seq-length', type=int, default=2048)
    parser.add_argument('--train-limit', type=int, default=4096)
    parser.add_argument('--learning-rate', type=float, default=1e-4)
    parser.add_argument('--lora-r', type=int, default=16)
    parser.add_argument('--lora-alpha', type=int, default=32)
    parser.add_argument('--grad-accum', type=int, default=16)
    parser.add_argument('--eval-limit', type=int, default=80)
    parser.add_argument('--max-train-tokens', type=int, default=512)
    parser.add_argument('--seed', type=int, default=42)
    parser.add_argument('--run-id')
    parser.add_argument('--output-root', default='/workspace/outputs/smoke')
    parser.add_argument('--report-root', default='/workspace/reports/smoke')
    return parser.parse_args()


if __name__ == '__main__':
    result = run_smoke(parse_args())
    print(json.dumps(result, indent=2, sort_keys=True))
