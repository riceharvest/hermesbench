"""Modal QLoRA smoke trainer for Hermes Qwen3.6 v0 SFT.

This is intentionally boring: prove load -> train a small capped run -> save adapter ->
reload-ish smoke generate -> write a report. It is not the MTP refresh stage.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import modal

APP_NAME = "qwen36-hermes-v0-sft-smoke"
MODEL_NAME = "unsloth/Qwen3.6-35B-A3B"
CONFIG_PATH = Path("/workspace/configs/qwen36-hermes-v0-sft.yaml")
TRAIN_PATH = Path("/workspace/data/processed/hermes_v0_train.jsonl")
VOLUME_OUTPUT_DIR = Path("/checkpoints/qwen36-hermes-v0-sft-smoke")
REPORT_PATH = Path("/checkpoints/reports/qwen36-hermes-v0-sft-smoke.json")

app = modal.App(APP_NAME)
hf_cache = modal.Volume.from_name("hf-cache", create_if_missing=True)
checkpoints = modal.Volume.from_name("qwen-mtp-probe-checkpoints", create_if_missing=True)

image = (
    modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.12")
    .pip_install(
        "torch",
        "accelerate",
        "bitsandbytes",
        "peft",
        "datasets",
        "pyyaml",
        "hf_transfer",
        "huggingface_hub[hf_transfer]",
        "transformers==5.0.0",
        "trl==0.19.1",
        "unsloth",
    )
    .add_local_dir("src", "/workspace/src", copy=True)
    .add_local_dir("configs", "/workspace/configs", copy=True)
    .add_local_dir("data/processed", "/workspace/data/processed", copy=True)
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "HF_XET_HIGH_PERFORMANCE": "1",
            "PYTHONPATH": "/workspace/src",
            "TOKENIZERS_PARALLELISM": "false",
            "PYTORCH_CUDA_ALLOC_CONF": "expandable_segments:True",
        }
    )
)


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
    messages = row.get("messages")
    if not isinstance(messages, list):
        raise ValueError("expected row.messages list")
    try:
        return tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=False)
    except Exception:
        # Fallback is deliberately simple and deterministic; the target still contains
        # the assistant ACTION/FINAL text and is only used if a remote tokenizer lacks a template.
        parts: list[str] = []
        for message in messages:
            role = message.get("role", "unknown")
            content = message.get("content", "")
            parts.append(f"{role.upper()}: {content}")
        return "\n".join(parts) + "\n"


def _tokenize_rows(tokenizer: Any, rows: list[dict[str, Any]], max_seq_length: int) -> list[dict[str, Any]]:
    tokenized: list[dict[str, Any]] = []
    for row in rows:
        text = _format_messages(tokenizer, row)
        encoded = tokenizer(
            text,
            truncation=True,
            max_length=max_seq_length,
            padding=False,
            return_attention_mask=True,
        )
        if len(encoded["input_ids"]) < 8:
            continue
        encoded["labels"] = list(encoded["input_ids"])
        tokenized.append(encoded)
    if not tokenized:
        raise ValueError("no usable tokenized examples")
    return tokenized


def _collate(tokenizer: Any, features: list[dict[str, Any]]) -> dict[str, Any]:
    import torch

    max_len = max(len(feature["input_ids"]) for feature in features)
    pad_id = tokenizer.pad_token_id if tokenizer.pad_token_id is not None else tokenizer.eos_token_id
    input_ids: list[list[int]] = []
    attention_mask: list[list[int]] = []
    labels: list[list[int]] = []
    for feature in features:
        pad = max_len - len(feature["input_ids"])
        input_ids.append(feature["input_ids"] + [pad_id] * pad)
        attention_mask.append(feature["attention_mask"] + [0] * pad)
        labels.append(feature["labels"] + [-100] * pad)
    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
    }


@app.function(
    image=image,
    gpu="A100-80GB",
    timeout=6 * 3600,
    scaledown_window=10,
    max_containers=1,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/checkpoints": checkpoints,
    },
)
def train_smoke(
    max_steps: int = 80,
    max_seq_length: int = 4096,
    train_limit: int = 1024,
    learning_rate: float = 1e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    grad_accum: int = 16,
) -> dict[str, Any]:
    started = time.time()
    report: dict[str, Any] = {
        "stage": "start",
        "model": MODEL_NAME,
        "gpu_request": "A100-80GB",
        "max_steps": max_steps,
        "max_seq_length": max_seq_length,
        "train_limit": train_limit,
        "learning_rate": learning_rate,
        "lora_r": lora_r,
        "lora_alpha": lora_alpha,
        "grad_accum": grad_accum,
        "error": None,
    }

    try:
        import torch
        import yaml
        from torch.utils.data import DataLoader
        from unsloth import FastLanguageModel

        torch.manual_seed(42)
        print("[sft-smoke] torch", torch.__version__, "cuda", torch.version.cuda, flush=True)
        print("[sft-smoke] gpu", torch.cuda.get_device_name(0), flush=True)

        config = yaml.safe_load(CONFIG_PATH.read_text())
        rows = _load_jsonl(TRAIN_PATH, limit=train_limit)
        report.update({"stage": "data", "loaded_rows": len(rows), "config_run_name": config["run_name"]})
        print(f"[sft-smoke] loaded {len(rows)} rows", flush=True)

        model, tokenizer = FastLanguageModel.from_pretrained(
            model_name=MODEL_NAME,
            max_seq_length=max_seq_length,
            dtype=torch.bfloat16,
            load_in_4bit=True,
            trust_remote_code=True,
        )
        if tokenizer.pad_token is None:
            tokenizer.pad_token = tokenizer.eos_token
        tokenizer.padding_side = "right"

        tokenized = _tokenize_rows(tokenizer, rows, max_seq_length=max_seq_length)
        lengths = [len(row["input_ids"]) for row in tokenized]
        report.update(
            {
                "stage": "tokenized",
                "tokenized_rows": len(tokenized),
                "min_tokens": min(lengths),
                "max_tokens": max(lengths),
                "avg_tokens": sum(lengths) / len(lengths),
                "cuda_memory_allocated_gb_after_4bit_load": torch.cuda.memory_allocated() / 1e9,
                "cuda_memory_reserved_gb_after_4bit_load": torch.cuda.memory_reserved() / 1e9,
            }
        )
        print("[sft-smoke] tokenized", report["tokenized_rows"], "avg_tokens", report["avg_tokens"], flush=True)

        lora_modules = config["lora"]["target_modules"]
        # Explicitly no router modules in v0-sft-main.
        lora_modules = [module for module in lora_modules if "router" not in module.lower()]
        model = FastLanguageModel.get_peft_model(
            model,
            r=lora_r,
            target_modules=lora_modules,
            lora_alpha=lora_alpha,
            lora_dropout=float(config["lora"].get("dropout", 0.05)),
            bias="none",
            use_gradient_checkpointing="unsloth",
            random_state=42,
        )
        FastLanguageModel.for_training(model)
        model.train()
        trainable_params, all_params = model.get_nb_trainable_parameters()
        report.update(
            {
                "stage": "model_loaded",
                "target_modules": lora_modules,
                "trainable_params": int(trainable_params),
                "all_params": int(all_params),
                "trainable_percent": float(trainable_params / all_params * 100),
                "cuda_memory_allocated_gb_loaded": torch.cuda.memory_allocated() / 1e9,
                "cuda_memory_reserved_gb_loaded": torch.cuda.memory_reserved() / 1e9,
            }
        )
        print("[sft-smoke] trainable", trainable_params, "of", all_params, flush=True)

        loader = DataLoader(
            tokenized,
            batch_size=1,
            shuffle=True,
            collate_fn=lambda features: _collate(tokenizer, features),
        )
        optimizer = torch.optim.AdamW(model.parameters(), lr=learning_rate)
        step_losses: list[float] = []
        optimizer_steps = 0
        micro_steps = 0
        optimizer.zero_grad(set_to_none=True)

        while optimizer_steps < max_steps:
            for batch in loader:
                batch = {key: value.to(model.device) for key, value in batch.items()}
                outputs = model(**batch)
                loss = outputs.loss / grad_accum
                loss.backward()
                micro_steps += 1
                if micro_steps % grad_accum == 0:
                    optimizer.step()
                    optimizer.zero_grad(set_to_none=True)
                    optimizer_steps += 1
                    value = float((loss.detach() * grad_accum).cpu())
                    step_losses.append(value)
                    print(f"[sft-smoke] step {optimizer_steps}/{max_steps} loss={value:.4f}", flush=True)
                    if optimizer_steps >= max_steps:
                        break

        VOLUME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        model.save_pretrained(VOLUME_OUTPUT_DIR)
        tokenizer.save_pretrained(VOLUME_OUTPUT_DIR)

        FastLanguageModel.for_inference(model)
        model.eval()
        prompt_messages = [
            {"role": "system", "content": "You are a coding agent. Keep responses terse and parseable."},
            {"role": "user", "content": "What time is it?"},
        ]
        prompt = tokenizer.apply_chat_template(prompt_messages, tokenize=False, add_generation_prompt=True)
        inputs = tokenizer(prompt, return_tensors="pt").to(model.device)
        with torch.no_grad():
            output_ids = model.generate(**inputs, max_new_tokens=64, do_sample=False, use_cache=True)
        generated = tokenizer.decode(output_ids[0][inputs["input_ids"].shape[1] :], skip_special_tokens=True)

        report.update(
            {
                "stage": "done",
                "optimizer_steps": optimizer_steps,
                "micro_steps": micro_steps,
                "initial_loss": step_losses[0] if step_losses else None,
                "final_loss": step_losses[-1] if step_losses else None,
                "loss_delta": (step_losses[0] - step_losses[-1]) if len(step_losses) >= 2 else None,
                "step_losses_tail": step_losses[-20:],
                "adapter_dir": str(VOLUME_OUTPUT_DIR),
                "smoke_generation": generated.strip(),
                "cuda_memory_allocated_gb_final": torch.cuda.memory_allocated() / 1e9,
                "cuda_memory_reserved_gb_final": torch.cuda.memory_reserved() / 1e9,
                "elapsed_seconds": time.time() - started,
            }
        )
        print("[sft-smoke] done", json.dumps({k: report[k] for k in ["initial_loss", "final_loss", "loss_delta"]}), flush=True)

    except Exception as exc:
        report.update(
            {
                "stage": report.get("stage", "error"),
                "error": repr(exc),
                "elapsed_seconds": time.time() - started,
            }
        )
        print("[sft-smoke] ERROR", repr(exc), flush=True)

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    checkpoints.commit()
    return report


@app.local_entrypoint()
def main(
    max_steps: int = 80,
    max_seq_length: int = 4096,
    train_limit: int = 1024,
    learning_rate: float = 1e-4,
    lora_r: int = 16,
    lora_alpha: int = 32,
    grad_accum: int = 16,
) -> None:
    report = train_smoke.remote(
        max_steps=max_steps,
        max_seq_length=max_seq_length,
        train_limit=train_limit,
        learning_rate=learning_rate,
        lora_r=lora_r,
        lora_alpha=lora_alpha,
        grad_accum=grad_accum,
    )
    print(json.dumps(report, indent=2, sort_keys=True))
